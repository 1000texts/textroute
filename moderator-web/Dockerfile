FROM node:20-alpine

WORKDIR /app

# Vite inlines env vars at build time, so the API base URL must be present
# during the image build as well as at runtime.
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5174
CMD ["npm", "run", "dev", "--", "--host"]
