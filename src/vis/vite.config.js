import { defineConfig } from 'vite';
import cesium from 'vite-plugin-cesium';
import { resolve } from 'path';

export default defineConfig({
  plugins: [cesium()],
  // 显式指定 public 目录和根目录
  publicDir: 'public', 
  root: './', 
  server: {
    host: true,
    fs: {
      allow: ['.']
    }
  }
});
