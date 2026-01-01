FROM node:20-alpine

WORKDIR /app

# 👇 Accept build arg
ARG VITE_API_BASE_URL

# 👇 Make it available to Vite
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

COPY package.json package-lock.json ./
RUN npm install

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host"]