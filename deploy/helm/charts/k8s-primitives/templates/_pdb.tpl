{{- define "k8s-primitives.pdb" -}}
{{- if .Values.pdb.enabled }}
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: {{ include "k8s-primitives.fullname" . }}
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "k8s-primitives.labels" . | nindent 4 }}
spec:
  minAvailable: {{ .Values.pdb.minAvailable }}
  selector:
    matchLabels:
      {{- include "k8s-primitives.selectorLabels" . | nindent 6 }}
{{- end }}
{{- end }}
