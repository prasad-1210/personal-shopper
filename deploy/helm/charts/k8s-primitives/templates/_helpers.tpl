{{/* k8s-primitives helpers — platform team maintains */}}

{{- define "k8s-primitives.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "k8s-primitives.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "k8s-primitives.labels" -}}
helm.sh/chart: {{ include "k8s-primitives.name" . }}-{{ .Chart.Version }}
app.kubernetes.io/name: {{ include "k8s-primitives.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "k8s-primitives.selectorLabels" -}}
app.kubernetes.io/name: {{ include "k8s-primitives.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "k8s-primitives.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "k8s-primitives.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
