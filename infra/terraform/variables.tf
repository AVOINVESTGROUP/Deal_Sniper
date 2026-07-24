variable "project_id" { type = string }
variable "region" {
  type    = string
  default = "me-central1"
}
variable "image" { type = string }
variable "api_base_url" { type = string }
variable "telegram_allowed_user_ids" { type = string }
variable "telegram_channel_id" {
  type    = string
  default = ""
}
variable "raw_bucket_name" { type = string }
variable "billing_account" {
  type    = string
  default = ""
}
variable "monthly_budget_aed" {
  type    = number
  default = 500
}

locals {
  runtime_sa       = "deal-sniper-runtime"
  scheduler_sa     = "deal-sniper-scheduler"
  sources          = toset(["dubicars", "carswitch", "cars24", "opensooq"])
  source_pages     = {
    dubicars  = 5
    carswitch = 5
    cars24    = 5
    opensooq  = 5
  }
  source_page_env  = {
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
