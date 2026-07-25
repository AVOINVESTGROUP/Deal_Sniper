output "api_url" { value = google_cloud_run_v2_service.api.uri }
output "raw_bucket" { value = google_storage_bucket.raw.name }
output "collector_jobs" { value = { for key, job in google_cloud_run_v2_job.collector : key => job.name } }
output "migration_job" { value = google_cloud_run_v2_job.migration.name }
output "hosting_url" { value = "https://${google_firebase_hosting_site.app.site_id}.web.app" }
