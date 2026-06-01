{{- define "k8s-primitives.secretRefReminder" -}}
{{- if .Values.secretRefReminder }}
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "k8s-primitives.fullname" . }}-secret-info
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "k8s-primitives.labels" . | nindent 4 }}
data:
  SECRET_NAME: {{ .Values.secretName | default (printf "%s-secrets" .Release.Name) | quote }}
  README: |
    The secret '{{ .Values.secretName | default (printf "%s-secrets" .Release.Name) }}'
    must be pre-created before deploying this chart.

    The langgraph build / wolfi image requires complete connection string URIs.
    REDIS_URI and DATABASE_URI must be full URIs, not assembled from Helm values.

    Redis DB index convention (each agent must use a unique index):
      supervisor:       redis://<host>:6379/0
      nutrition-agent:  redis://<host>:6379/1
      recipe-agent:     redis://<host>:6379/2
      shopping-agent:   redis://<host>:6379/3
      budget-agent:     redis://<host>:6379/4

    Create the secret:
      kubectl create secret generic {{ .Values.secretName | default (printf "%s-secrets" .Release.Name) }} \
        --namespace {{ .Release.Namespace }} \
        --from-literal=OPENAI_API_KEY=<value> \
        --from-literal=LANGSMITH_API_KEY=<value> \
        --from-literal=KROGER_CLIENT_ID=<value> \
        --from-literal=KROGER_CLIENT_SECRET=<value> \
        --from-literal=EDAMAM_APP_ID=<value> \
        --from-literal=EDAMAM_APP_KEY=<value> \
        --from-literal=RAPIDAPI_KEY=<value> \
        --from-literal=REDIS_URI="redis://<host>:6379/<db-index>" \
        --from-literal=DATABASE_URI="postgres://<user>:<pass>@<host>:5432/<database>" \
        --from-literal=LANGGRAPH_CLOUD_LICENSE_KEY=<value-or-empty>

    Azure Key Vault CSI (AKS production):
      https://learn.microsoft.com/azure/aks/csi-secrets-store-driver
      Sync Key Vault secrets to a K8s Secret; the wolfi image reads env vars only.
{{- end }}
{{- end }}
