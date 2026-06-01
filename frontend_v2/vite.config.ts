import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { readFileSync } from 'fs'
import { resolve } from 'path'

// 从 server_port.json 自动读取后端端口和前端端口
let backendPort = 5500
let frontendPort = 5380
try {
  const portFile = resolve(__dirname, '..', 'server_port.json')
  const data = JSON.parse(readFileSync(portFile, 'utf-8'))
  if (data.port) backendPort = data.port
  if (data.frontend_port) frontendPort = data.frontend_port
  console.log(`✅ 后端端口: ${backendPort}, 前端端口: ${frontendPort}`)
} catch {
  console.log(`⚠️ 未找到 server_port.json，使用默认端口 (后端:${backendPort}, 前端:${frontendPort})`)
}

const apiProxy = {
  '/api': {
    target: `http://127.0.0.1:${backendPort}`,
    changeOrigin: true,
    timeout: 1200000,      // 20 minutes timeout
    proxyTimeout: 1200000, // 20 minutes proxy timeout
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: frontendPort,
    host: '127.0.0.1',
    proxy: apiProxy,
  },
  preview: {
    port: frontendPort,
    host: '127.0.0.1',
    proxy: apiProxy,
  }
})
