# Strapi v5 E2E Test Instance
FROM node:20-alpine

# Install build dependencies for native modules (better-sqlite3)
RUN apk add --no-cache python3 make g++ git

WORKDIR /opt/strapi

# Copy package files first for better caching
COPY package.json package-lock.json* ./

# Install dependencies with legacy peer deps to handle version conflicts
RUN npm install --legacy-peer-deps

# Copy the rest of the application
COPY . .

# Expose Strapi port
EXPOSE 1337

# Set environment variables
ENV NODE_ENV=development
ENV HOST=0.0.0.0
ENV PORT=1337

# Run Strapi in development mode (builds admin on first run)
# This avoids build issues and is appropriate for E2E testing
CMD ["npm", "run", "develop"]
