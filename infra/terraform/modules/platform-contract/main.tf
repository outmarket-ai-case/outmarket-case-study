terraform {
  required_version = ">= 1.6"
}

locals {
  # Templated rather than materialised: the pipeline substitutes the password
  # from the secret store at deploy time, so no credential ever enters state.
  connection_url_template = format(
    "postgresql+asyncpg://%s:__PASSWORD__@%s:%d/%s",
    var.database.username, var.database.host, var.database.port, var.database.name
  )
}
