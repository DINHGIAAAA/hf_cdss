FROM node:20-alpine AS builder

WORKDIR /app

COPY doctor-dashboard/package*.json ./
RUN npm install

COPY shared ./shared
COPY doctor-dashboard/ .

ARG VITE_API_BASE_URL
ARG VITE_API_KEY
ARG VITE_API_KEY_HEADER
ARG VITE_CHAT_LANGUAGE

ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_API_KEY=$VITE_API_KEY
ENV VITE_API_KEY_HEADER=$VITE_API_KEY_HEADER
ENV VITE_CHAT_LANGUAGE=$VITE_CHAT_LANGUAGE

RUN npm run build

FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY doctor-dashboard/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
