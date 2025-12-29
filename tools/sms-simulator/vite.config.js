import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
    plugins: [react()],
    server: {
        host: true,       // bind to 0.0.0.0 (required for Docker)
        port: 5173,       // force port
        strictPort: true  // FAIL if port is unavailable
    }
})
