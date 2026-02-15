package com.example.learning.agent.ui.screens.map

import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.example.learning.agent.ui.theme.TekLearningAgentTheme

@Composable
fun MapScreen(
    modifier: Modifier = Modifier
) {
    var showWebView by remember { mutableStateOf(false) }

    if (showWebView) {
        WebViewContent(
            url = "https://example.com",
            onBack = { showWebView = false }
        )
    } else {
        Column(
            modifier = modifier
                .fillMaxSize()
                .padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(16.dp),
                elevation = CardDefaults.cardElevation(defaultElevation = 4.dp)
            ) {
                Column(
                    modifier = Modifier.padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(
                        text = "Mind Map",
                        style = MaterialTheme.typography.headlineMedium,
                        modifier = Modifier.padding(bottom = 16.dp)
                    )
                    Text(
                        text = "This will open a Mind Map web view showing your learning connections and knowledge graph.",
                        style = MaterialTheme.typography.bodyLarge,
                        modifier = Modifier.padding(bottom = 24.dp)
                    )
                    Button(
                        onClick = { showWebView = true },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text("Open Map")
                    }
                }
            }
        }
    }
}

@Composable
fun WebViewContent(
    url: String,
    onBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    AndroidView(
        factory = { context ->
            WebView(context).apply {
                webViewClient = WebViewClient()
                settings.javaScriptEnabled = true
                loadUrl(url)
            }
        },
        modifier = modifier.fillMaxSize()
    )
}

@Preview(showBackground = true)
@Composable
fun MapScreenPreview() {
    TekLearningAgentTheme {
        MapScreen()
    }
}

