import type { CapacitorConfig } from "@capacitor/cli";

const remoteUrl = process.env.FITCLAW_PWA_URL || "http://84.46.249.133:8000/app";

const config: CapacitorConfig = {
  appId: "com.fitclaw.aiops",
  appName: "FitClaw AI Ops",
  webDir: "www",
  bundledWebRuntime: false,
  server: {
    url: remoteUrl,
    cleartext: remoteUrl.startsWith("http://"),
    androidScheme: "http",
  },
};

export default config;
