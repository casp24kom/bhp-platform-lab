terraform {
  backend "azurerm" {
    resource_group_name  = "rg-bhp-platformlab-tfstate-dev-ae"
    storage_account_name = "stbhpplabtfdevauae"
    container_name       = "tfstate"
    key                  = "aws/dev/terraform.tfstate"
    use_azuread_auth     = true
  }
}