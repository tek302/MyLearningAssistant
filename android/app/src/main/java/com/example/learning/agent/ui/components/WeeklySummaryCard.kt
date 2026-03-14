package com.example.learning.agent.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ThumbDown
import androidx.compose.material.icons.filled.ThumbUp
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.example.learning.agent.data.remote.S2Api

@Composable
fun WeeklySummaryCard(
    summary: S2Api.S2SummaryItem,
    onOpen: () -> Unit,
    onReprocess: () -> Unit,
    onThumbsUp: () -> Unit = {},
    onThumbsDown: () -> Unit = {},
    feedbackAction: String? = null,
    feedbackSubmitting: Boolean = false,
    isReprocessing: Boolean = false,
    modifier: Modifier = Modifier
) {
    val weekLabel = summary.extra?.weekStart?.let { "Week of $it" }
        ?: summary.extra?.topicName ?: "This Week"
    val bullets = summary.bullets?.filter { it.isNotBlank() }.orEmpty()
    val showBullets = bullets.take(3)

    Card(
        modifier = modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
        ) {
            Text(
                text = weekLabel,
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.primary,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            summary.tldr?.takeIf { it.isNotBlank() }?.let { tldr ->
                Text(
                    text = tldr,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 3,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.padding(top = 8.dp, bottom = 4.dp)
                )
            }
            showBullets.forEach { bullet ->
                Row(
                    modifier = Modifier.padding(vertical = 2.dp),
                    horizontalArrangement = Arrangement.Start
                ) {
                    Text(
                        text = "• ",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.primary
                    )
                    Text(
                        text = bullet,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f)
                    )
                }
            }
            if (bullets.size > 3) {
                Text(
                    text = "+${bullets.size - 3} more",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.8f),
                    modifier = Modifier.padding(top = 4.dp)
                )
            }
            Spacer(modifier = Modifier.height(12.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.End
            ) {
                if (feedbackSubmitting) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(16.dp),
                        strokeWidth = 2.dp
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                }
                IconButton(onClick = onThumbsUp, enabled = !feedbackSubmitting) {
                    Icon(
                        imageVector = Icons.Default.ThumbUp,
                        contentDescription = "Helpful summary",
                        tint = if (feedbackAction == "thumbs_up") MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                IconButton(onClick = onThumbsDown, enabled = !feedbackSubmitting) {
                    Icon(
                        imageVector = Icons.Default.ThumbDown,
                        contentDescription = "Not helpful summary",
                        tint = if (feedbackAction == "thumbs_down") MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                TextButton(onClick = onOpen) {
                    Text("Open")
                }
                TextButton(
                    onClick = onReprocess,
                    enabled = !isReprocessing
                ) {
                    if (isReprocessing) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(16.dp),
                            strokeWidth = 2.dp
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                    }
                    Text(if (isReprocessing) "Re-generating…" else "Re-process")
                }
            }
        }
    }
}
