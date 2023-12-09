module "knowledge-bot" {
  source = "git::ssh://git@github.com/LedgerHQ/tf-aws-ledger-apps.git//knowledge-bot"
  # Application variables
  env = "stg"

  # Aws provider configuration
  profile = "454902641012"
  region  = "eu-west-1"

  # Tags for billing
  tags = {
    terraform    = "true"
    owner        = "team-ms@ledger.fr"
    service_id   = "2081"
    project      = "2081"
    environment  = "stg"
    organization = "enterprise"
    service      = "knowledge-bot"
    tenancy      = "dedicated"
  }

  openai_api_key   = "AQICAHhsae32ubcJUfBxRld9Jod8R6krFMPg/QC9FWAZ5xxqOQEXtb2KjapdsRI8dL3rNUomAAAAlTCBkgYJKoZIhvcNAQcGoIGEMIGBAgEAMHwGCSqGSIb3DQEHATAeBglghkgBZQMEAS4wEQQM041gK0cb45IAfxvEAgEQgE+2W7ZJDtd/ByC+gE4kF6iSKMqUB80L0astEZwI4+ytNFSpnQuD10BeNhQHxUwatcrAP8wRWRydBqi61KLjyu80YorQO/zfv1vGSwHZM9Eu"
  alchemy_api_key  = "AQICAHhsae32ubcJUfBxRld9Jod8R6krFMPg/QC9FWAZ5xxqOQFb5jSLF3FtZKoe48atRF/7AAAAfzB9BgkqhkiG9w0BBwagcDBuAgEAMGkGCSqGSIb3DQEHATAeBglghkgBZQMEAS4wEQQMdZLNsi+AmQ43iUvJAgEQgDwlWnSXQyS0V75xe37orELYLy43p5dAJE6Fk8L5VyHpgOiSDMwhLeYeTgPaaPjLE2jPRBeCQf4Sp5jmJpo="
  pinecone_api_key = "AQICAHhsae32ubcJUfBxRld9Jod8R6krFMPg/QC9FWAZ5xxqOQGZ+Q7aIn1G3QLINbeizcEMAAAAhDCBgQYJKoZIhvcNAQcGoHQwcgIBADBtBgkqhkiG9w0BBwEwHgYJYIZIAWUDBAEuMBEEDJhPuEXSLmrWZVDHFgIBEIBAWN4xhzqfoKrIb4GdAEI6EW9EYmZ4E1kzEyvOxrINL52ERm4r1Nkd3xKu2iGrCFjt23uyWP227mQPWqbLdyqL0g=="
}
