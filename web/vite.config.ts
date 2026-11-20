import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The app reads shared data from tools/ and agent/ one level up.
export default defineConfig({ plugins: [react()], base: "./", server: { fs: { allow: [".."] } } });
