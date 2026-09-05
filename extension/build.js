import { build } from 'vite';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import fs from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

async function runBuild() {
  console.log('🚀 Building VoiceForm Chrome Extension (M1)...');

  const distDir = resolve(__dirname, 'dist');

  // Ensure clean dist directory
  if (fs.existsSync(distDir)) {
    fs.rmSync(distDir, { recursive: true, force: true });
  }
  fs.mkdirSync(distDir, { recursive: true });

  // 1. Build Content Script (IIFE for isolated execution on any page)
  console.log('📦 Bundling Content Script...');
  await build({
    configFile: false,
    build: {
      outDir: distDir,
      emptyOutDir: false,
      lib: {
        entry: resolve(__dirname, 'src/content/index.ts'),
        name: 'VoiceFormContent',
        formats: ['iife'],
        fileName: () => 'content.js'
      }
    }
  });

  // 2. Build Background Service Worker (ES Module for MV3)
  console.log('📦 Bundling Background Service Worker...');
  await build({
    configFile: false,
    build: {
      outDir: distDir,
      emptyOutDir: false,
      lib: {
        entry: resolve(__dirname, 'src/background/service-worker.ts'),
        formats: ['es'],
        fileName: () => 'background.js'
      }
    }
  });

  // 3. Build Popup HTML & assets
  console.log('📦 Bundling Popup UI...');
  await build({
    configFile: false,
    root: resolve(__dirname, 'src/popup'),
    base: './',
    build: {
      outDir: resolve(__dirname, 'dist'),
      emptyOutDir: false,
      rollupOptions: {
        input: {
          popup: resolve(__dirname, 'src/popup/popup.html')
        },
        output: {
          entryFileNames: '[name].js',
          assetFileNames: '[name].[ext]'
        }
      }
    }
  });

  // 4. Copy manifest.json to dist
  console.log('📄 Copying manifest.json...');
  fs.copyFileSync(
    resolve(__dirname, 'manifest.json'),
    resolve(distDir, 'manifest.json')
  );

  console.log('✅ VoiceForm Extension build complete! Artifacts in extension/dist/');
}

runBuild().catch((err) => {
  console.error('❌ Build failed:', err);
  process.exit(1);
});
