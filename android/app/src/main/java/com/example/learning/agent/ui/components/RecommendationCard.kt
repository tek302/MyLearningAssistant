package com.example.learning.agent.ui.components

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.OpenInNew
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.ThumbDown
import androidx.compose.material.icons.filled.ThumbUp
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.learning.agent.data.models.Recommendation
import com.example.learning.agent.data.remote.RecommendationsApi
import com.example.learning.agent.data.repository.RecommendationsRepository
import kotlinx.coroutines.launch

@Composable
fun RecommendationCard(
    recommendation: Recommendation,
    onProcess: () -> Unit = {},
    onRemove: () -> Unit = {},
    onThumbsUp: () -> Unit = {},
    onThumbsDown: () -> Unit = {},
    feedbackAction: String? = null,
    feedbackSubmitting: Boolean = false,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var abstractExpanded by remember { mutableStateOf(false) }
    val abstractText = recommendation.abstract?.trim()?.ifEmpty { null }
    val maxAbstractLines = if (abstractExpanded) Int.MAX_VALUE else 3

    var explanation by remember { mutableStateOf<RecommendationsApi.ExplanationResponse?>(null) }
    var showExplanation by remember { mutableStateOf(false) }
    var explanationLoading by remember { mutableStateOf(false) }

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
            Text(
                text = recommendation.title,
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(bottom = 8.dp)
            )

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

            // Keyword tags (from explanation)
            val keywords = explanation?.triggeringKeywords
            if (showExplanation && keywords != null && keywords.isNotEmpty()) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .horizontalScroll(rememberScrollState())
                        .padding(vertical = 4.dp),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    keywords.forEach { kw ->
                        AssistChip(
                            onClick = {},
                            label = {
                                Text(
                                    kw.keyword,
                                    style = MaterialTheme.typography.labelSmall,
                                    fontWeight = if (kw.contribution == "primary") FontWeight.Bold else FontWeight.Normal
                                )
                            },
                            modifier = Modifier.height(26.dp)
                        )
                    }
                }
            }

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
                Row {
                    IconButton(
                        onClick = {
                            if (!showExplanation && explanation == null && !explanationLoading) {
                                explanationLoading = true
                                scope.launch {
                                    when (val r = RecommendationsRepository.getExplanation(recommendation.id)) {
                                        is RecommendationsRepository.ExplanationResult.Success -> explanation = r.data
                                        is RecommendationsRepository.ExplanationResult.Error -> { /* silently fail */ }
                                    }
                                    explanationLoading = false
                                    showExplanation = true
                                }
                            } else {
                                showExplanation = !showExplanation
                            }
                        },
                        modifier = Modifier.size(32.dp)
                    ) {
                        if (explanationLoading) {
                            CircularProgressIndicator(modifier = Modifier.size(14.dp), strokeWidth = 2.dp)
                        } else {
                            Icon(
                                Icons.Default.Info,
                                contentDescription = "Why this?",
                                modifier = Modifier.size(18.dp),
                                tint = if (showExplanation) MaterialTheme.colorScheme.primary
                                       else MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
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
            }

            Spacer(modifier = Modifier.height(8.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.End,
                verticalAlignment = Alignment.CenterVertically
            ) {
                if (feedbackSubmitting) {
                    CircularProgressIndicator(modifier = Modifier.size(16.dp), strokeWidth = 2.dp)
                    Spacer(modifier = Modifier.width(8.dp))
                }
                IconButton(onClick = onThumbsUp, enabled = !feedbackSubmitting) {
                    Icon(
                        imageVector = Icons.Default.ThumbUp,
                        contentDescription = "Helpful",
                        tint = if (feedbackAction == "thumbs_up") MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                IconButton(onClick = onThumbsDown, enabled = !feedbackSubmitting) {
                    Icon(
                        imageVector = Icons.Default.ThumbDown,
                        contentDescription = "Not helpful",
                        tint = if (feedbackAction == "thumbs_down") MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            recommendation.score?.let { score ->
                Spacer(modifier = Modifier.height(12.dp))
                ScoreBar(score = score)
            }

            Spacer(modifier = Modifier.height(12.dp))

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
