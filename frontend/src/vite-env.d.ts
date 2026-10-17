// Typed view of the build-time variables Vite exposes; vite/client supplies the rest.
interface ImportMetaEnv {
  readonly VITE_BACKEND_URL?: string;
}
