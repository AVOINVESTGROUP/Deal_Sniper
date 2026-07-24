data "google_project" "current" {}

resource "google_project_service" "apis" {
  for_each = toset([
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudscheduler.googleapis.com",
    "cloudtasks.googleapis.com",
    "firestore.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "app" {
  location      = var.region
  repository_id = "deal-sniper"
  format        = "DOCKER"
  depends_on    = [google_project_service.apis]
}

resource "google_storage_bucket" "raw" {
  name                        = var.raw_bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  versioning { enabled = true }
}

resource "google_service_account" "runtime" {
  account_id   = local.runtime_sa
  display_name = "Dubai Deal Sniper runtime"
}

resource "google_service_account" "scheduler" {
  account_id   = local.scheduler_sa
  display_name = "Dubai Deal Sniper scheduler"
}

resource "google_secret_manager_secret" "telegram_token" {
  secret_id = "telegram-bot-token"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "webhook_secret" {
  secret_id = "telegram-webhook-secret"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "task_secret" {
  secret_id = "internal-task-secret"
  replication {
    auto {}
  }
}

resource "google_cloud_tasks_queue" "processing" {
  name     = "listing-processing"
  location = var.region
  rate_limits {
    max_concurrent_dispatches = 5
    max_dispatches_per_second = 5
  }
  retry_config {
    max_attempts = 5
    min_backoff  = "5s"
    max_backoff  = "300s"
  }
}

resource "google_cloud_tasks_queue" "delivery" {
  name     = "telegram-delivery"
  location = var.region
  rate_limits {
    max_concurrent_dispatches = 5
    max_dispatches_per_second = 10
  }
  retry_config {
    max_attempts = 8
    min_backoff  = "5s"
    max_backoff  = "600s"
  }
}

resource "google_cloud_run_v2_service" "api" {
  name     = "deal-sniper-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.runtime.email
    timeout         = "300s"
    scaling { max_instance_count = 3 }
    containers {
      image = var.image
      resources { limits = { cpu = "1", memory = "512Mi" } }
      dynamic "env" {
        for_each = {
          GOOGLE_CLOUD_PROJECT         = var.project_id
          GOOGLE_CLOUD_REGION          = var.region
          STORAGE_BACKEND              = "firestore"
          RAW_SNAPSHOTS_BUCKET         = google_storage_bucket.raw.name
          CLOUD_TASKS_LOCATION         = var.region
          LISTING_PROCESSING_QUEUE     = google_cloud_tasks_queue.processing.name
          TELEGRAM_DELIVERY_QUEUE      = google_cloud_tasks_queue.delivery.name
          TASK_INVOKER_SERVICE_ACCOUNT = google_service_account.runtime.email
          COLLECTOR_JOB_PREFIX         = "deal-sniper-collector"
          TELEGRAM_ALLOWED_USER_IDS    = var.telegram_allowed_user_ids
          TELEGRAM_CHANNEL_ID          = var.telegram_channel_id
          MIN_COMPARABLES_COUNT        = "5"
        }
        content {
          name  = env.key
          value = env.value
        }
      }
      env {
        name  = "CLOUD_RUN_API_URL"
        value = var.api_base_url
      }
      env {
        name = "TELEGRAM_BOT_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.telegram_token.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "TELEGRAM_WEBHOOK_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.webhook_secret.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "INTERNAL_TASK_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.task_secret.secret_id
            version = "latest"
          }
        }
      }
    }
  }
}

resource "google_cloud_run_v2_job" "collector" {
  for_each = local.sources
  name     = "deal-sniper-collector-${each.key}"
  location = var.region
  template {
    template {
      service_account = google_service_account.runtime.email
      timeout         = "600s"
      max_retries     = 2
      containers {
        image   = var.image
        command = ["python"]
        args    = ["main.py", "collect", "--source", each.key]
        dynamic "env" {
          for_each = merge({
            GOOGLE_CLOUD_PROJECT         = var.project_id
            GOOGLE_CLOUD_REGION          = var.region
            STORAGE_BACKEND              = "firestore"
            RAW_SNAPSHOTS_BUCKET         = google_storage_bucket.raw.name
            CLOUD_RUN_API_URL            = var.api_base_url
            CLOUD_TASKS_LOCATION         = var.region
            LISTING_PROCESSING_QUEUE     = google_cloud_tasks_queue.processing.name
            TELEGRAM_DELIVERY_QUEUE      = google_cloud_tasks_queue.delivery.name
            TASK_INVOKER_SERVICE_ACCOUNT = google_service_account.runtime.email
            MIN_COMPARABLES_COUNT        = "5"
          }, { (local.source_page_env[each.key]) = tostring(local.source_pages[each.key]) })
          content {
            name  = env.key
            value = env.value
          }
        }
        env {
          name = "INTERNAL_TASK_SECRET"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.task_secret.secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }
}

resource "google_cloud_run_v2_job" "publisher" {
  name     = "deal-sniper-publisher"
  location = var.region
  template {
    template {
      service_account = google_service_account.runtime.email
      timeout         = "600s"
      max_retries     = 2
      containers {
        image   = var.image
        command = ["python"]
        args    = ["main.py", "publish"]
        dynamic "env" {
          for_each = {
            GOOGLE_CLOUD_PROJECT      = var.project_id
            GOOGLE_CLOUD_REGION       = var.region
            STORAGE_BACKEND           = "firestore"
            RAW_SNAPSHOTS_BUCKET      = google_storage_bucket.raw.name
            TELEGRAM_CHANNEL_ID       = var.telegram_channel_id
            CHANNEL_MAX_POSTS_PER_RUN = "10"
            MIN_COMPARABLES_COUNT     = "5"
          }
          content {
            name  = env.key
            value = env.value
          }
        }
        env {
          name = "TELEGRAM_BOT_TOKEN"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.telegram_token.secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }
}

resource "google_cloud_scheduler_job" "collector" {
  for_each         = local.sources
  name             = "deal-sniper-${each.key}-every-10m"
  region           = var.region
  schedule         = local.source_schedules[each.key]
  time_zone        = "Asia/Dubai"
  attempt_deadline = "180s"
  retry_config {
    retry_count          = 2
    min_backoff_duration = "10s"
    max_backoff_duration = "300s"
  }
  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.collector[each.key].name}:run"
    oauth_token { service_account_email = google_service_account.scheduler.email }
  }
}

resource "google_project_iam_member" "runtime_roles" {
  for_each = toset(["roles/datastore.user", "roles/cloudtasks.enqueuer", "roles/logging.logWriter", "roles/monitoring.metricWriter", "roles/run.invoker", "roles/secretmanager.secretAccessor"])
  project  = var.project_id
  role     = each.key
  member   = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_storage_bucket_iam_member" "raw_writer" {
  bucket = google_storage_bucket.raw.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_project_iam_member" "scheduler_run" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.scheduler.email}"
}

resource "google_service_account_iam_member" "tasks_token" {
  service_account_id = google_service_account.runtime.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-cloudtasks.iam.gserviceaccount.com"
}
