{{- define "k8s-primitives.ingress" -}}
{{- if .Values.ingress.enabled }}
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ include "k8s-primitives.fullname" . }}
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "k8s-primitives.labels" . | nindent 4 }}
  {{- with .Values.ingress.annotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
spec:
  ingressClassName: {{ .Values.ingress.className }}
  {{- with .Values.ingress.tls }}
  tls:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  rules:
    {{- range .Values.ingress.hosts }}
    - host: {{ .host }}
      http:
        paths:
          {{- range .paths }}
          - path: {{ .path }}
            pathType: {{ .pathType | default "Prefix" }}
            backend:
              service:
                name: {{ .serviceName | default (include "k8s-primitives.fullname" $) }}
                port:
                  number: {{ .servicePort | default $.Values.service.port }}
          {{- end }}
    {{- end }}
{{- end }}
{{- end }}
