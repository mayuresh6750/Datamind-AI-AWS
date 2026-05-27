variable "supabase_project_id" {
  description = "Supabase project ID"
  type        = string
}

variable "supabase_access_token" {
  description = "Supabase management API access token"
  type        = string
  sensitive   = true
}

variable "supabase_db_password" {
  description = "PostgreSQL database password for Supabase"
  type        = string
  sensitive   = true
}

variable "app_env" {
  description = "Deployment environment (staging | production)"
  type        = string
  default     = "staging"
}

variable "ghcr_image_backend" {
  description = "GHCR image URI for the FastAPI backend"
  type        = string
}

variable "ghcr_image_frontend" {
  description = "GHCR image URI for the Next.js frontend"
  type        = string
}

variable "allowed_origins" {
  description = "Comma-separated list of allowed CORS origins"
  type        = string
  default     = "http://localhost:3000"
}
