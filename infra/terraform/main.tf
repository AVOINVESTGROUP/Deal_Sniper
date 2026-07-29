data "google_project" "current" {}

resource "google_project_service" "apis" {
  for_each = toset([
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudscheduler.googleapis.com",
    "cloudtasks.googleapis.com",
    "firestore.googleapis.com",
    "firebase.googleapis.com",
    "firebasehosting.googleapis.com",
    "identitytoolkit.googleapis.com",
    "monitoring.googleapis.com",
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
  retention_policy { retention_period = 31536000 }
}

resource "google_storage_bucket" "firestore_exports" {
  name                        = var.firestore_export_bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  versioning { enabled = true }
  retention_policy { retention_period = 31536000 }
}

resource "google_service_account" "runtime" {
  account_id   = local.runtime_sa
  display_name = "Dubai Deal Sniper runtime"
}

resource "google_service_account" "scheduler" {
  account_id   = local.scheduler_sa
  display_name = "Dubai Deal Sniper scheduler"
}

resource "google_service_account" "collector" {
  account_id   = local.collector_sa
  display_name = "Dubai Deal Sniper collectors"
}

resource "google_service_account" "migration" {
  account_id   = local.migration_sa
  display_name = "Dubai Deal Sniper migration"
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

resource "google_secret_manager_secret" "whatsapp_token" {
  secret_id = "whatsapp-access-token"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "whatsapp_webhook" {
  secret_id = "whatsapp-webhook-secret"
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

resource "google_cloud_tasks_queue" "delivery_staging" {
  name     = "telegram-delivery-staging"
  location = var.region
  rate_limits {
    max_concurrent_dispatches = 1
    max_dispatches_per_second = 1
  }
  retry_config {
    max_attempts = 3
    min_backoff  = "10s"
    max_backoff  = "300s"
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
          DEPLOYMENT_ENVIRONMENT       = var.deployment_environment
          FIRESTORE_DATABASE           = var.firestore_database
          STORAGE_BACKEND              = "firestore"
          RAW_SNAPSHOTS_BUCKET         = google_storage_bucket.raw.name
          CLOUD_TASKS_LOCATION         = var.region
          LISTING_PROCESSING_QUEUE     = google_cloud_tasks_queue.processing.name
          TELEGRAM_DELIVERY_QUEUE      = google_cloud_tasks_queue.delivery.name
          TASK_INVOKER_SERVICE_ACCOUNT = google_service_account.runtime.email
          COLLECTOR_JOB_PREFIX         = "deal-sniper-collector"
          TELEGRAM_ALLOWED_USER_IDS    = var.telegram_allowed_user_ids
          TELEGRAM_ADMIN_USER_IDS      = var.telegram_admin_user_ids
          ADMIN_EMAILS                 = var.admin_emails
          TELEGRAM_CHANNEL_ID          = var.telegram_channel_id
          TELEGRAM_PRO_CHANNEL_ID      = var.telegram_pro_channel_id
          TMA_URL                      = var.firebase_hosting_url
          FREE_TEASER_IMAGE_URL        = "${trimsuffix(var.firebase_hosting_url, "/")}/assets/verified-deal-signal.png"
          DELIVERY_ENABLED             = tostring(var.delivery_enabled)
          GIT_COMMIT                   = var.git_commit
          RUNTIME_IMAGE_DIGEST         = var.runtime_image_digest
          SCHEMA_VERSION               = "2"
          MIGRATION_TOOL_VERSION       = "1.0.0"
          FINANCIAL_CONFIG_VERSION     = var.financial_config_version
          WHATSAPP_ENABLED             = "false"
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
      service_account = google_service_account.collector.email
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
            DEPLOYMENT_ENVIRONMENT       = var.deployment_environment
            FIRESTORE_DATABASE           = var.firestore_database
            STORAGE_BACKEND              = "firestore"
            RAW_SNAPSHOTS_BUCKET         = google_storage_bucket.raw.name
            CLOUD_RUN_API_URL            = var.api_base_url
            CLOUD_TASKS_LOCATION         = var.region
            LISTING_PROCESSING_QUEUE     = google_cloud_tasks_queue.processing.name
            TELEGRAM_DELIVERY_QUEUE      = google_cloud_tasks_queue.delivery.name
            TASK_INVOKER_SERVICE_ACCOUNT = google_service_account.collector.email
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

resource "google_cloud_run_v2_job" "migration" {
  name     = "deal-sniper-migration"
  location = var.region
  template {
    template {
      service_account = google_service_account.migration.email
      timeout         = "3600s"
      max_retries     = 0
      containers {
        image   = var.image
        command = ["python"]
        args    = ["-m", "src.migration"]
        env {
          name  = "GOOGLE_CLOUD_PROJECT"
          value = var.project_id
        }
        env {
          name  = "FIRESTORE_DATABASE"
          value = var.firestore_database
        }
        env {
          name  = "MIGRATION_CUTOVER_AT"
          value = var.migration_cutover_at
        }
        env {
          name  = "EXPORT_WATERMARK"
          value = var.migration_export_watermark
        }
      }
    }
  }
}

resource "google_cloud_run_v2_job" "replay" {
  name     = "deal-sniper-replay"
  location = var.region
  template {
    template {
      service_account = google_service_account.runtime.email
      timeout         = "3600s"
      max_retries     = 0
      containers {
        image   = var.image
        command = ["python"]
        args    = ["main.py", "replay"]
        dynamic "env" {
          for_each = {
            GOOGLE_CLOUD_PROJECT         = var.project_id
            DEPLOYMENT_ENVIRONMENT       = var.deployment_environment
            FIRESTORE_DATABASE           = var.firestore_database
            STORAGE_BACKEND              = "firestore"
            DELIVERY_ENABLED             = "false"
            CLOUD_RUN_API_URL            = var.api_base_url
            CLOUD_TASKS_LOCATION         = var.region
            LISTING_PROCESSING_QUEUE     = google_cloud_tasks_queue.processing.name
            TELEGRAM_DELIVERY_QUEUE      = google_cloud_tasks_queue.delivery.name
            TASK_INVOKER_SERVICE_ACCOUNT = google_service_account.runtime.email
          }
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

resource "google_cloud_run_v2_job" "content" {
  name     = "deal-sniper-content"
  location = var.region
  template {
    template {
      service_account = google_service_account.runtime.email
      timeout         = "300s"
      max_retries     = 1
      containers {
        image   = var.image
        command = ["python"]
        args    = ["main.py", "content"]
        dynamic "env" {
          for_each = {
            GOOGLE_CLOUD_PROJECT         = var.project_id
            GOOGLE_CLOUD_REGION          = var.region
            DEPLOYMENT_ENVIRONMENT       = var.deployment_environment
            FIRESTORE_DATABASE           = var.firestore_database
            STORAGE_BACKEND              = "firestore"
            CLOUD_RUN_API_URL            = var.api_base_url
            CLOUD_TASKS_LOCATION         = var.region
            TELEGRAM_DELIVERY_QUEUE      = google_cloud_tasks_queue.delivery.name
            TASK_INVOKER_SERVICE_ACCOUNT = google_service_account.runtime.email
            TELEGRAM_CHANNEL_ID          = var.telegram_channel_id
          }
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

resource "google_cloud_scheduler_job" "collector" {
  for_each         = local.sources
  name             = "deal-sniper-${each.key}-every-10m"
  region           = var.region
  schedule         = local.source_schedules[each.key]
  paused           = !var.production_enabled
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

resource "google_cloud_scheduler_job" "content" {
  name             = "deal-sniper-weekly-market-pulse"
  region           = var.region
  schedule         = "0 10 * * 6"
  time_zone        = "Asia/Dubai"
  paused           = !var.production_enabled
  attempt_deadline = "180s"
  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.content.name}:run"
    oauth_token { service_account_email = google_service_account.scheduler.email }
  }
}

resource "google_cloud_run_v2_service_iam_member" "api_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_project_iam_member" "runtime_roles" {
  for_each = toset(["roles/datastore.user", "roles/cloudtasks.enqueuer", "roles/cloudtasks.viewer", "roles/cloudscheduler.viewer", "roles/logging.logWriter", "roles/monitoring.metricWriter", "roles/run.invoker", "roles/run.viewer"])
  project  = var.project_id
  role     = each.key
  member   = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_project_iam_custom_role" "runtime_scheduler_operator" {
  role_id     = "dealSniperSchedulerOperator"
  title       = "Deal Sniper Scheduler Operator"
  description = "Минимальные права Control Center для allowlisted Scheduler jobs"
  permissions = [
    "cloudscheduler.jobs.get",
    "cloudscheduler.jobs.list",
    "cloudscheduler.jobs.run",
    "cloudscheduler.jobs.pause",
    "cloudscheduler.jobs.enable",
  ]
}

resource "google_project_iam_member" "runtime_scheduler_operator" {
  project = var.project_id
  role    = google_project_iam_custom_role.runtime_scheduler_operator.name
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_project_iam_member" "collector_roles" {
  for_each = toset(["roles/datastore.user", "roles/cloudtasks.enqueuer", "roles/logging.logWriter", "roles/monitoring.metricWriter", "roles/run.invoker"])
  project  = var.project_id
  role     = each.key
  member   = "serviceAccount:${google_service_account.collector.email}"
}

resource "google_project_iam_member" "migration_roles" {
  for_each = toset(["roles/datastore.user", "roles/logging.logWriter"])
  project  = var.project_id
  role     = each.key
  member   = "serviceAccount:${google_service_account.migration.email}"
}

resource "google_secret_manager_secret_iam_member" "runtime_secrets" {
  for_each = {
    telegram = google_secret_manager_secret.telegram_token.id
    webhook  = google_secret_manager_secret.webhook_secret.id
    tasks    = google_secret_manager_secret.task_secret.id
  }
  project   = var.project_id
  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_storage_bucket_iam_member" "raw_writer" {
  bucket = google_storage_bucket.raw.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.collector.email}"
}

resource "google_storage_bucket_iam_member" "migration_export_reader" {
  bucket = google_storage_bucket.firestore_exports.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.migration.email}"
}

resource "google_project_iam_member" "scheduler_run" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.scheduler.email}"
}

resource "google_service_account_iam_member" "tasks_token" {
  service_account_id = google_service_account.collector.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-cloudtasks.iam.gserviceaccount.com"
}

resource "google_service_account_iam_member" "tasks_token_runtime" {
  service_account_id = google_service_account.runtime.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-cloudtasks.iam.gserviceaccount.com"
}

resource "google_firebase_project" "app" {
  provider   = google-beta
  project    = var.project_id
  depends_on = [google_project_service.apis]
}

resource "google_firebase_hosting_site" "app" {
  provider = google-beta
  project  = var.project_id
  site_id  = var.project_id
  app_id   = google_firebase_project.app.id
}

resource "google_billing_budget" "monthly" {
  count           = var.billing_account == "" ? 0 : 1
  billing_account = "billingAccounts/${var.billing_account}"
  display_name    = "Dubai Deal Sniper monthly budget"
  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(ceil(var.monthly_budget_aed / 3.6725))
    }
  }
  threshold_rules { threshold_percent = 0.5 }
  threshold_rules { threshold_percent = 0.8 }
  threshold_rules { threshold_percent = 1.0 }
}
