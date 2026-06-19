FROM node:20-alpine AS builder

WORKDIR /app

COPY admin/package*.json ./
RUN npm install

COPY shared ./shared
COPY admin/ .

ARG VITE_API_BASE_URL
ARG VITE_API_KEY
ARG VITE_API_KEY_HEADER
ARG VITE_DOCTOR_DASHBOARD_URL

ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_API_KEY=$VITE_API_KEY
ENV VITE_API_KEY_HEADER=$VITE_API_KEY_HEADER
ENV VITE_DOCTOR_DASHBOARD_URL=$VITE_DOCTOR_DASHBOARD_URL

RUN npm run build

FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY admin/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
