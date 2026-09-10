{{- define "idea-board.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "idea-board.fullname" -}}
{{- printf "%s" (include "idea-board.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "idea-board.labels" -}}
app.kubernetes.io/name: {{ include "idea-board.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Values.image.tag | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: idea-board
idea-board.io/cloud: {{ .Values.platform.cloud }}
idea-board.io/environment: {{ .Values.platform.environment }}
{{- end -}}

{{- define "idea-board.selectorLabels" -}}
app.kubernetes.io/name: {{ include "idea-board.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "idea-board.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "idea-board.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/*
Fully-qualified image reference. Registry facts come from the contract, so the
same template resolves to an ECR URI or an Artifact Registry URI untouched.
*/}}
{{- define "idea-board.image" -}}
{{- $component := index . 1 -}}
{{- with (index . 0) -}}
{{- if .Values.platform.registry.host -}}
{{ .Values.platform.registry.host }}/{{ .Values.platform.registry.repositoryPrefix }}/{{ $component }}:{{ .Values.image.tag }}
{{- else -}}
idea-board-{{ $component }}:{{ .Values.image.tag }}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "idea-board.dbSecretName" -}}
{{ include "idea-board.fullname" . }}-db
{{- end -}}

{{/* The password secret: either created by External Secrets or pre-existing. */}}
{{- define "idea-board.dbSecretRef" -}}
{{- if .Values.externalSecrets.enabled -}}
{{ include "idea-board.dbSecretName" . }}
{{- else -}}
{{ required "database.passwordSecret is required when externalSecrets.enabled=false" .Values.database.passwordSecret }}
{{- end -}}
{{- end -}}

{{/* Ingress annotations: the only place a cloud name appears in the chart. */}}
{{- define "idea-board.ingressAnnotations" -}}
{{- $class := .Values.platform.cluster.ingressClass -}}
{{- $defaults := dict -}}
{{- if eq $class "alb" -}}
{{- $defaults = dict "alb.ingress.kubernetes.io/scheme" "internet-facing" "alb.ingress.kubernetes.io/target-type" "ip" "alb.ingress.kubernetes.io/healthcheck-path" "/nginx-health" -}}
{{- else if eq $class "gce" -}}
{{- $defaults = dict "kubernetes.io/ingress.class" "gce" -}}
{{- else if eq $class "nginx" -}}
{{- $defaults = dict "nginx.ingress.kubernetes.io/proxy-body-size" "1m" -}}
{{- end -}}
{{- toYaml (merge (deepCopy .Values.ingress.annotations) $defaults) -}}
{{- end -}}
