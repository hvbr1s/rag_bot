{{/*
Create datadog labels
*/}}
{{- define "knowledge-bot.datadogLabels" -}}
tags.datadoghq.com/env: {{ .env }}
tags.datadoghq.com/service: {{ .service }}
tags.datadoghq.com/version: {{ .version }}
{{- end }}
