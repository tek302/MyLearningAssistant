package com.example.learning.agent.ui.components

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.OpenInNew
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.example.learning.agent.data.models.Recommendation

@Composable
fun RecommendationCard(
    recommendation: Recommendation,
    onProcess: () -> Unit = {},
    onRemove: () -> Unit = {},
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    var abstractExpanded by remember { mutableStateOf(false) }
    val abstractText = recommendation.abstract?.trim()?.ifEmpty { null }
    val maxAbstractLines = if (abstractExpanded) Int.MAX_VALUE else 3

    Card(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 8.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
        ) {
            // Title
            Text(
                text = recommendation.title,
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(bottom = 8.dp)
            )

            // Abstract (expandable)
            if (abstractText != null) {
                Text(
                    text = abstractText,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = maxAbstractLines,
                    modifier = Modifier.padding(bottom = 4.dp)
                )
                if (abstractText.length > 180) {
                    TextButton(
                        onClick = { abstractExpanded = !abstractExpanded },
                        contentPadding = PaddingValues(0.dp)
                    ) {
                        Text(if (abstractExpanded) "Show less" else "Show more")
                    }
                }
            }

            // Source, date, and link to original
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "${recommendation.source} · ${recommendation.displayDate.ifEmpty { "" }}".trimEnd(' ', '·', ' '),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                if (recommendation.url.isNotBlank()) {
                    TextButton(
                        onClick = {
                            context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(recommendation.url)))
                        },
                        contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp)
                    ) {
                        Icon(Icons.AutoMirrored.Filled.OpenInNew, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("Original", style = MaterialTheme.typography.labelMedium)
                    }
                }
            }

            // Optional score bar
            recommendation.score?.let { score ->
                Spacer(modifier = Modifier.height(12.dp))
                ScoreBar(score = score)
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Actions: Process (ingest + remove from list), Remove (delete only)
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Button(onClick = onProcess) {
                    Text("Process")
                }
                OutlinedButton(onClick = onRemove) {
                    Text("Remove")
                }
            }
        }
    }
}

@Composable
fun ScoreBar(
    score: Float,
    modifier: Modifier = Modifier
) {
    Column(modifier = modifier) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text(
                text = "Relevance Score",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Text(
                text = "${(score * 100).toInt()}%",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.primary
            )
        }
        Spacer(modifier = Modifier.height(4.dp))
        LinearProgressIndicator(
            progress = { score },
            modifier = Modifier
                .fillMaxWidth()
                .height(8.dp),
            color = MaterialTheme.colorScheme.primary,
            trackColor = MaterialTheme.colorScheme.surfaceVariant
        )
    }
}
