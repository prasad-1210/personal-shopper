{{/* langgraph-primitives helpers */}}

{{- define "langgraph-primitives.agentName" -}}
{{- .Values.agent.name | required "agent.name is required" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "langgraph-primitives.fullname" -}}
{{- include "langgraph-primitives.agentName" . }}
{{- end }}

{{- define "langgraph-primitives.labels" -}}
app.kubernetes.io/name: {{ include "langgraph-primitives.agentName" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: {{ .Values.agent.type | default "sub-agent" }}
app.kubernetes.io/part-of: personal-shopper
langgraph/agent: {{ include "langgraph-primitives.agentName" . }}
langgraph/graph-id: {{ .Values.agent.graphId | default .Values.agent.name | quote }}
{{- end }}

{{- define "langgraph-primitives.selectorLabels" -}}
app.kubernetes.io/name: {{ include "langgraph-primitives.agentName" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "langgraph-primitives.secretName" -}}
{{- .Values.secretName | default "personal-shopper-secrets" }}
{{- end }}

{{- define "langgraph-primitives.isUi" -}}
{{- eq .Values.agent.type "ui" -}}
{{- end }}

{{- define "langgraph-primitives.containerPort" -}}
{{- .Values.agent.port | default 8000 }}
{{- end }}

{{- define "langgraph-primitives.k8sService" -}}
{{- $port := include "langgraph-primitives.containerPort" . | int -}}
{{- $svc := merge (dict "type" "ClusterIP" "port" $port "targetPort" $port) (.Values.service | default dict) -}}
{{- $_ := set $svc "port" $port -}}
{{- $_ := set $svc "targetPort" $port -}}
{{- $vals := merge .Values (dict "nameOverride" (include "langgraph-primitives.agentName" .) "fullnameOverride" (include "langgraph-primitives.fullname" .) "service" $svc) -}}
{{- $ctx := dict "Values" $vals "Release" .Release "Chart" (dict "Name" "k8s-primitives" "Version" "1.0.0") -}}
{{- include "k8s-primitives.service" $ctx -}}
{{- end }}

{{- define "langgraph-primitives.k8sHpa" -}}
{{- $port := include "langgraph-primitives.containerPort" . | int -}}
{{- $svc := merge (dict "type" "ClusterIP" "port" $port "targetPort" $port) (.Values.service | default dict) -}}
{{- $_ := set $svc "port" $port -}}
{{- $_ := set $svc "targetPort" $port -}}
{{- $vals := merge .Values (dict "nameOverride" (include "langgraph-primitives.agentName" .) "fullnameOverride" (include "langgraph-primitives.fullname" .) "service" $svc) -}}
{{- $ctx := dict "Values" $vals "Release" .Release "Chart" (dict "Name" "k8s-primitives" "Version" "1.0.0") -}}
{{- include "k8s-primitives.hpa" $ctx -}}
{{- end }}

{{- define "langgraph-primitives.k8sPdb" -}}
{{- $port := include "langgraph-primitives.containerPort" . | int -}}
{{- $svc := merge (dict "type" "ClusterIP" "port" $port "targetPort" $port) (.Values.service | default dict) -}}
{{- $_ := set $svc "port" $port -}}
{{- $_ := set $svc "targetPort" $port -}}
{{- $vals := merge .Values (dict "nameOverride" (include "langgraph-primitives.agentName" .) "fullnameOverride" (include "langgraph-primitives.fullname" .) "service" $svc) -}}
{{- $ctx := dict "Values" $vals "Release" .Release "Chart" (dict "Name" "k8s-primitives" "Version" "1.0.0") -}}
{{- include "k8s-primitives.pdb" $ctx -}}
{{- end }}

{{- define "langgraph-primitives.k8sServiceAccount" -}}
{{- $port := include "langgraph-primitives.containerPort" . | int -}}
{{- $svc := merge (dict "type" "ClusterIP" "port" $port "targetPort" $port) (.Values.service | default dict) -}}
{{- $_ := set $svc "port" $port -}}
{{- $_ := set $svc "targetPort" $port -}}
{{- $vals := merge .Values (dict "nameOverride" (include "langgraph-primitives.agentName" .) "fullnameOverride" (include "langgraph-primitives.fullname" .) "service" $svc) -}}
{{- $ctx := dict "Values" $vals "Release" .Release "Chart" (dict "Name" "k8s-primitives" "Version" "1.0.0") -}}
{{- include "k8s-primitives.serviceAccount" $ctx -}}
{{- end }}

{{- define "langgraph-primitives.k8sIngress" -}}
{{- $port := include "langgraph-primitives.containerPort" . | int -}}
{{- $svc := merge (dict "type" "ClusterIP" "port" $port "targetPort" $port) (.Values.service | default dict) -}}
{{- $_ := set $svc "port" $port -}}
{{- $_ := set $svc "targetPort" $port -}}
{{- $vals := merge .Values (dict "nameOverride" (include "langgraph-primitives.agentName" .) "fullnameOverride" (include "langgraph-primitives.fullname" .) "service" $svc) -}}
{{- $ctx := dict "Values" $vals "Release" .Release "Chart" (dict "Name" "k8s-primitives" "Version" "1.0.0") -}}
{{- include "k8s-primitives.ingress" $ctx -}}
{{- end }}

{{- define "langgraph-primitives.k8sSecretRefReminder" -}}
{{- $port := include "langgraph-primitives.containerPort" . | int -}}
{{- $svc := merge (dict "type" "ClusterIP" "port" $port "targetPort" $port) (.Values.service | default dict) -}}
{{- $_ := set $svc "port" $port -}}
{{- $_ := set $svc "targetPort" $port -}}
{{- $vals := merge .Values (dict "nameOverride" (include "langgraph-primitives.agentName" .) "fullnameOverride" (include "langgraph-primitives.fullname" .) "service" $svc "secretName" (include "langgraph-primitives.secretName" .)) -}}
{{- $ctx := dict "Values" $vals "Release" .Release "Chart" (dict "Name" "k8s-primitives" "Version" "1.0.0") -}}
{{- include "k8s-primitives.secretRefReminder" $ctx -}}
{{- end }}
