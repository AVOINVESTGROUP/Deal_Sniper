# Terraform

Каталог описывает production-контур: Storage, Secret Manager, Cloud Run API,
четыре collector Jobs, Cloud Tasks, Scheduler, service accounts и IAM.

Секретные значения Terraform не создаёт. После `terraform apply` добавьте версии
секретов через Secret Manager. Для уже существующего окружения `avo-deal-sniper`
сначала выполните `terraform import` для ресурсов с теми же именами; не запускайте
`apply` поверх созданных вручную ресурсов без импорта.

```powershell
Copy-Item terraform.tfvars.example terraform.tfvars
terraform init
terraform fmt -check
terraform validate
terraform plan
```
