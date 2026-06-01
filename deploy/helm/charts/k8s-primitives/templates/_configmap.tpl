{{- define "k8s-primitives.configmap" -}}
{{- if .Values.configMap.data }}
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "k8s-primitives.fullname" . }}-config
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "k8s-primitives.labels" . | nindent 4 }}
data:
  {{- toYaml .Values.configMap.data | nindent 2 }}
{{- end }}
{{- end }}
