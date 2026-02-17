import { contextBridge } from 'electron';
import { createElectronAPI } from './api';

// Create the unified API by combining all domain-specific APIs
const electronAPI = createElectronAPI();

// Expose to renderer via contextBridge
contextBridge.exposeInMainWorld('electronAPI', electronAPI);

// Expose debug flag for debug logging
contextBridge.exposeInMainWorld('DEBUG', process.env.DEBUG === 'true');

// Expose platform information for platform-specific behavior (e.g., PTY resize timing)
// SECURITY NOTE: process.platform used directly here because preload scripts cannot
// import from main process modules (platform/). This is safe as process.platform is
// a read-only constant, not user input.
contextBridge.exposeInMainWorld('platform', {
  isWindows: process.platform === 'win32',
  isMacOS: process.platform === 'darwin',
  isLinux: process.platform === 'linux',
  isUnix: process.platform !== 'win32',
});
