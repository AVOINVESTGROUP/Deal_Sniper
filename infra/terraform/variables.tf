variable "project_id" { type = string }
variable "region" {
  type    = string
  default = "me-central1"
}
variable "deployment_environment" {
  type    = string
  default = "production"
  validation {
    condition     = contains(["staging", "production"], var.deployment_environment)
    error_message = "deployment_environment должен быть staging или production"
  }
}
variable "image" { type = string }
variable "api_base_url" { type = string }
variable "firestore_database" {
  type    = string
  default = "(default)"
}
variable "telegram_allowed_user_ids" { type = string }
variable "telegram_admin_user_ids" {
  type    = string
  default = ""
}
variable "admin_emails" {
  type    = string
  default = ""
}
variable "delivery_enabled" {
  type    = bool
  default = false
}
variable "production_enabled" {
  type    = bool
  default = false
}
variable "telegram_channel_id" {
  type    = string
  default = ""
}
variable "telegram_pro_channel_id" {
  type    = string
  default = ""
}
variable "firebase_hosting_url" {
  type    = string
  default = ""
}
variable "raw_bucket_name" { type = string }
variable "firestore_export_bucket_name" { type = string }
variable "git_commit" {
  type    = string
  default = "unknown"
}
variable "runtime_image_digest" {
  type    = string
  default = "unknown"
}
variable "financial_config_version" {
  type    = string
  default = "provisional-2026-07-v1"
}
variable "migration_cutover_at" {
  type    = string
  default = "2026-07-25T09:27:20.616Z"
}
variable "migration_export_watermark" {
  type    = string
  default = "2026-07-25T09:27:20.616Z"
}
variable "billing_account" {
  type    = string
  default = ""
}
variable "monthly_budget_aed" {
  type    = number
  default = 500
}

locals {
  runtime_sa   = "deal-sniper-runtime"
  collector_sa = "deal-sniper-collector"
  migration_sa = "deal-sniper-migration"
  scheduler_sa = "deal-sniper-scheduler"
  sources      = toset(["dubicars", "carswitch", "cars24", "opensooq"])
  source_pages = {
    dubicars  = 5
    carswitch = 5
    cars24    = 5
    opensooq  = 5
  }
  source_page_env = {
    dubicars  = "DUBICARS_MAX_PAGES"
    carswitch = "CARSWITCH_MAX_PAGES"
    cars24    = "CARS24_MAX_PAGES"
    opensooq  = "OPENSOOQ_MAX_PAGES"
  }
  source_schedules = {
    dubicars  = "0/10 * * * *"
    carswitch = "2/10 * * * *"
    cars24    = "4/10 * * * *"
    opensooq  = "6/10 * * * *"
  }
}
