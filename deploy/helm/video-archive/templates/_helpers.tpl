{{/* Release-scoped resource name: <fullname>, defaults to the chart name. */}}
{{- define "video-archive.fullname" -}}
{{- default .Chart.Name .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Common labels attached to every object. */}}
{{- define "video-archive.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/* Component image references. */}}
{{- define "video-archive.backendImage" -}}
{{ .Values.image.registry }}/{{ .Values.image.backend.repository }}:{{ .Values.image.backend.tag }}
{{- end -}}

{{- define "video-archive.frontendImage" -}}
{{ .Values.image.registry }}/{{ .Values.image.frontend.repository }}:{{ .Values.image.frontend.tag }}
{{- end -}}
