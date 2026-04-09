package com.personalaiops.agent;

import android.app.Activity;
import android.os.Bundle;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.os.Build;
import org.json.JSONObject;

public class MainActivity extends Activity {

    private WebView webView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Dark status bar
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            Window w = getWindow();
            w.addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);
            w.setStatusBarColor(Color.parseColor("#0b1120"));
            w.setNavigationBarColor(Color.parseColor("#0b1120"));
        }

        webView = new WebView(this);
        webView.setBackgroundColor(Color.parseColor("#0b1120"));

        WebSettings ws = webView.getSettings();
        ws.setJavaScriptEnabled(true);
        ws.setDomStorageEnabled(true);
        ws.setAllowFileAccess(true);
        ws.setDatabaseEnabled(true);

        webView.addJavascriptInterface(new AgentBridge(), "AgentBridge");
        webView.setWebViewClient(new WebViewClient());
        webView.loadUrl("file:///android_asset/setup.html");

        setContentView(webView);
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    /** JavaScript bridge callable from the WebView. */
    private class AgentBridge {

        @JavascriptInterface
        public String testConnection(String configJson) {
            try {
                JSONObject cfg = new JSONObject(configJson);
                String base = cfg.optString("api_base_url", "").replaceAll("/+$", "");
                if (base.isEmpty()) return "Error: no server URL";

                java.net.URL url = new java.net.URL(base + "/health");
                java.net.HttpURLConnection conn = (java.net.HttpURLConnection) url.openConnection();
                conn.setConnectTimeout(8000);
                conn.setReadTimeout(8000);
                int code = conn.getResponseCode();
                conn.disconnect();
                if (code >= 200 && code < 300) {
                    return "Server reachable (HTTP " + code + ")";
                }
                return "Server returned HTTP " + code;
            } catch (Exception e) {
                return "Connection failed: " + e.getMessage();
            }
        }

        @JavascriptInterface
        public String saveConfig(String configJson) {
            try {
                SharedPreferences prefs = getSharedPreferences("agent_config", MODE_PRIVATE);
                prefs.edit().putString("config", configJson).apply();
                return "Configuration saved to device.";
            } catch (Exception e) {
                return "Save failed: " + e.getMessage();
            }
        }

        @JavascriptInterface
        public String installAndStart(String configJson) {
            try {
                SharedPreferences prefs = getSharedPreferences("agent_config", MODE_PRIVATE);
                prefs.edit().putString("config", configJson).apply();
                return "Config saved. Background agent service is not yet available on Android.";
            } catch (Exception e) {
                return "Install failed: " + e.getMessage();
            }
        }

        @JavascriptInterface
        public String removeAgent(String configJson) {
            try {
                SharedPreferences prefs = getSharedPreferences("agent_config", MODE_PRIVATE);
                prefs.edit().clear().apply();
                return "Local config removed.";
            } catch (Exception e) {
                return "Removal failed: " + e.getMessage();
            }
        }

        @JavascriptInterface
        public String removeAutoStart(String configJson) {
            return "Auto-start not applicable on Android.";
        }

        @JavascriptInterface
        public void exit() {
            runOnUiThread(() -> finish());
        }
    }
}
