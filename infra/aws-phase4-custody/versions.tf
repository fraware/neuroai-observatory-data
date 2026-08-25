terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.60"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = merge(
      {
        Project     = "neuroai-observatory-data"
        Component   = "phase4-acquisition-custody"
        ManagedBy   = "terraform"
        DataClass   = "restricted-acquisition-evidence"
      },
      var.tags,
    )
  }
}
