{{- define "k8s-primitives.service" -}}
apiVersion: v1
kind: Service
metadata:
  name: {{ include "k8s-primitives.fullname" . }}
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "k8s-primitives.labels" . | nindent 4 }}
  {{- with .Values.service.annotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
spec:
  type: {{ .Values.service.type }}
  selector:
    {{- include "k8s-primitives.selectorLabels" . | nindent 4 }}
  ports:
    - name: http
      port: {{ .Values.service.port }}
      targetPort: {{ .Values.service.targetPort }}
      protocol: TCP
{{- end }}
