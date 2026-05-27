terraform {
  required_version = ">= 1.7"
  required_providers {
    supabase = {
      source  = "supabase/supabase"
      version = "~> 1.0"
    }
  }

  # Remote state — update bucket/key for your project
  backend "s3" {
    bucket = "datamind-tfstate"
    key    = "datamind/terraform.tfstate"
    region = "us-east-1"
  }
}

provider "supabase" {
  access_token = var.supabase_access_token
}

# ─── Supabase Storage Buckets ─────────────────────────────────────────────────

resource "supabase_storage_bucket" "archive" {
  project  = var.supabase_project_id
  name     = "datamind-archive"
  public   = false

  lifecycle {
    prevent_destroy = true
  }
}

resource "supabase_storage_bucket" "json_store" {
  project  = var.supabase_project_id
  name     = "datamind-json"
  public   = false

  lifecycle {
    prevent_destroy = true
  }
}

# ─── Outputs (used by CI deploy) ──────────────────────────────────────────────

output "archive_bucket" {
  value = supabase_storage_bucket.archive.name
}

output "json_bucket" {
  value = supabase_storage_bucket.json_store.name
}
