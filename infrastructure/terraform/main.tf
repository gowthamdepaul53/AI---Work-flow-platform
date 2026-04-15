# =============================================================================
# Terraform — GCP Infrastructure for AI Workflow Platform
# Provisions: GKE cluster, Cloud SQL (PostgreSQL), VPC, IAM
# =============================================================================

terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
  }

  # Remote state — GCS bucket
  backend "gcs" {
    bucket = "ai-platform-tfstate"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.gcp_project
  region  = var.gcp_region
}

# ---------------------------------------------------------------------------
# VPC
# ---------------------------------------------------------------------------
resource "google_compute_network" "platform_vpc" {
  name                    = "${var.environment}-ai-platform-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "platform_subnet" {
  name          = "${var.environment}-ai-platform-subnet"
  ip_cidr_range = "10.0.0.0/16"
  region        = var.gcp_region
  network       = google_compute_network.platform_vpc.self_link

  secondary_ip_range {
    range_name    = "gke-pods"
    ip_cidr_range = "10.1.0.0/16"
  }
  secondary_ip_range {
    range_name    = "gke-services"
    ip_cidr_range = "10.2.0.0/16"
  }
}

# ---------------------------------------------------------------------------
# GKE Cluster
# ---------------------------------------------------------------------------
resource "google_container_cluster" "platform_cluster" {
  name     = "${var.environment}-ai-platform-cluster"
  location = var.gcp_zone

  # Separate node pool (remove default)
  remove_default_node_pool = true
  initial_node_count       = 1

  network    = google_compute_network.platform_vpc.self_link
  subnetwork = google_compute_subnetwork.platform_subnet.self_link

  ip_allocation_policy {
    cluster_secondary_range_name  = "gke-pods"
    services_secondary_range_name = "gke-services"
  }

  # Workload Identity (Zero-Trust: pods get GCP SA, not node SA)
  workload_identity_config {
    workload_pool = "${var.gcp_project}.svc.id.goog"
  }

  # Private cluster
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }
}

# ---------------------------------------------------------------------------
# Node Pool — AI workloads (CPU-optimized)
# ---------------------------------------------------------------------------
resource "google_container_node_pool" "platform_nodes" {
  name       = "${var.environment}-ai-platform-nodes"
  location   = var.gcp_zone
  cluster    = google_container_cluster.platform_cluster.name

  node_count = var.min_node_count

  autoscaling {
    min_node_count = var.min_node_count
    max_node_count = var.max_node_count
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    machine_type = "n2-standard-4"   # 4 vCPU, 16GB RAM
    disk_size_gb = 100
    disk_type    = "pd-ssd"

    # Workload Identity on nodes
    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]

    labels = {
      environment = var.environment
      app         = "ai-platform"
    }

    tags = ["ai-platform-node"]
  }
}

# ---------------------------------------------------------------------------
# Cloud SQL — PostgreSQL 15
# ---------------------------------------------------------------------------
resource "google_sql_database_instance" "platform_db" {
  name             = "${var.environment}-ai-platform-db"
  database_version = "POSTGRES_15"
  region           = var.gcp_region

  settings {
    tier              = "db-custom-4-16384"   # 4 vCPU, 16GB RAM
    availability_type = var.environment == "prod" ? "REGIONAL" : "ZONAL"
    disk_size         = 100
    disk_autoresize   = true

    backup_configuration {
      enabled                        = true
      start_time                     = "03:00"
      point_in_time_recovery_enabled = true
    }

    ip_configuration {
      ipv4_enabled    = false   # Private IP only (Zero-Trust)
      private_network = google_compute_network.platform_vpc.self_link
    }

    insights_config {
      query_insights_enabled = true
    }
  }

  deletion_protection = var.environment == "prod"
}

resource "google_sql_database" "platform_db" {
  name     = "platform_db"
  instance = google_sql_database_instance.platform_db.name
}

resource "google_sql_user" "platform_user" {
  name     = "platform"
  instance = google_sql_database_instance.platform_db.name
  password = var.db_password   # Use Secret Manager in prod
}

# ---------------------------------------------------------------------------
# IAM — Workload Identity binding
# ---------------------------------------------------------------------------
resource "google_service_account" "platform_sa" {
  account_id   = "${var.environment}-ai-platform-sa"
  display_name = "AI Platform Service Account"
}

resource "google_project_iam_member" "platform_sa_roles" {
  for_each = toset([
    "roles/cloudsql.client",
    "roles/secretmanager.secretAccessor",
    "roles/monitoring.metricWriter",
    "roles/cloudtrace.agent",
  ])

  project = var.gcp_project
  role    = each.value
  member  = "serviceAccount:${google_service_account.platform_sa.email}"
}
