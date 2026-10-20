import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
const target=process.env.API_TARGET||'http://127.0.0.1:8000';
export default defineConfig({plugins:[react(),tailwindcss()],server:{watch:{ignored:['**/playwright-report/**','**/test-results/**','**/dist/**','**/*.tsbuildinfo']},proxy:{'/api':target,'/docs':target,'/openapi.json':target}}});
