package com.example.learning.agent.ui.components

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.example.learning.agent.data.remote.KeywordsApi

@Composable
fun KeywordSectionHeader(title: String, subtitle: String, icon: ImageVector) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 12.dp, horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(
            icon,
            contentDescription = null,
            modifier = Modifier.size(20.dp),
            tint = MaterialTheme.colorScheme.primary
        )
        Spacer(Modifier.width(8.dp))
        Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.width(8.dp))
        Text(
            subtitle,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

@Composable
fun KeywordManageCard(
    keyword: KeywordsApi.KeywordItem,
    onArchive: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp)
            .animateContentSize(),
        colors = CardDefaults.cardColors(
            containerColor = if (keyword.status == "declining")
                MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.3f)
            else MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    keyword.keyword,
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = FontWeight.Medium
                )
                Spacer(Modifier.height(2.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(
                        "w: ${"%.2f".format(keyword.weight)}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    val sourceLabel = when (keyword.source) {
                        "user_explicit" -> "explicit"
                        "stage1_accepted" -> "suggested"
                        else -> keyword.source
                    }
                    Text(
                        sourceLabel,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.primary
                    )
                    val up = keyword.paperFeedbackUp ?: 0
                    val down = keyword.paperFeedbackDown ?: 0
                    if (up > 0 || down > 0) {
                        Text(
                            "+$up / -$down",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }
            IconButton(onClick = onArchive) {
                Icon(
                    Icons.Default.Close,
                    contentDescription = "Archive",
                    tint = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

@Composable
fun KeywordSuggestionManageCard(
    suggestion: KeywordsApi.SuggestionItem,
    onAccept: () -> Unit,
    onReject: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.4f)
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    Icons.Default.AutoAwesome,
                    contentDescription = null,
                    modifier = Modifier.size(18.dp),
                    tint = MaterialTheme.colorScheme.primary
                )
                Spacer(Modifier.width(8.dp))
                Text(
                    suggestion.keyword,
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.weight(1f)
                )
                suggestion.suggestionType?.let { type ->
                    KeywordSuggestionTypeChip(type)
                }
            }
            suggestion.reason?.takeIf { it.isNotBlank() }?.let { reason ->
                Text(
                    reason,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.padding(top = 4.dp, start = 26.dp)
                )
            }
            suggestion.parentKeyword?.takeIf { it.isNotBlank() }?.let { parent ->
                Text(
                    "Related to: $parent",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary.copy(alpha = 0.7f),
                    modifier = Modifier.padding(top = 2.dp, start = 26.dp)
                )
            }
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 8.dp),
                horizontalArrangement = Arrangement.End,
                verticalAlignment = Alignment.CenterVertically
            ) {
                OutlinedButton(
                    onClick = onReject,
                    colors = ButtonDefaults.outlinedButtonColors(
                        contentColor = MaterialTheme.colorScheme.error
                    )
                ) {
                    Icon(Icons.Default.Close, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("Skip")
                }
                Spacer(Modifier.width(8.dp))
                Button(onClick = onAccept) {
                    Icon(Icons.Default.Check, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("Add")
                }
            }
        }
    }
}

@Composable
fun KeywordSuggestionTypeChip(type: String) {
    val label = when (type) {
        "derivative" -> "Derivative"
        "emerging" -> "Emerging"
        "cross_domain" -> "Cross-domain"
        "deepening" -> "Deepening"
        else -> type.replaceFirstChar { it.uppercase() }
    }
    AssistChip(
        onClick = {},
        label = { Text(label, style = MaterialTheme.typography.labelSmall) },
        modifier = Modifier.height(24.dp)
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddKeywordDialog(
    onDismiss: () -> Unit,
    onAdd: (String) -> Unit
) {
    var text by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add Research Keyword") },
        text = {
            OutlinedTextField(
                value = text,
                onValueChange = { text = it },
                label = { Text("Keyword") },
                placeholder = { Text("e.g., graph RAG, agent memory") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
        },
        confirmButton = {
            TextButton(
                onClick = { if (text.isNotBlank()) onAdd(text.trim()) },
                enabled = text.isNotBlank()
            ) { Text("Add") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        }
    )
}

/**
 * Full list for bottom sheet: pending suggestions + active + declining keywords with archive.
 */
@Composable
fun KeywordProfileManageList(
    keywords: List<KeywordsApi.KeywordItem>,
    suggestions: List<KeywordsApi.SuggestionItem>,
    onAcceptSuggestion: (KeywordsApi.SuggestionItem) -> Unit,
    onRejectSuggestion: (KeywordsApi.SuggestionItem) -> Unit,
    onArchiveKeyword: (KeywordsApi.KeywordItem) -> Unit,
    modifier: Modifier = Modifier,
    contentPadding: PaddingValues = PaddingValues(horizontal = 16.dp, vertical = 8.dp)
) {
    val active = keywords.filter { it.status == "active" }
    val declining = keywords.filter { it.status == "declining" }

    LazyColumn(
        modifier = modifier.fillMaxWidth(),
        contentPadding = contentPadding,
        verticalArrangement = Arrangement.spacedBy(0.dp)
    ) {
        if (suggestions.isNotEmpty()) {
            item {
                KeywordSectionHeader(
                    title = "Suggested Keywords",
                    subtitle = "${suggestions.size} pending",
                    icon = Icons.Default.Lightbulb
                )
            }
            items(suggestions, key = { it.id }) { suggestion ->
                KeywordSuggestionManageCard(
                    suggestion = suggestion,
                    onAccept = { onAcceptSuggestion(suggestion) },
                    onReject = { onRejectSuggestion(suggestion) }
                )
            }
            item { Spacer(Modifier.height(8.dp)) }
        }

        if (active.isNotEmpty()) {
            item {
                KeywordSectionHeader(
                    title = "Active Keywords",
                    subtitle = "${active.size} keywords",
                    icon = Icons.Default.Tag
                )
            }
            items(active, key = { it.id }) { kw ->
                KeywordManageCard(keyword = kw, onArchive = { onArchiveKeyword(kw) })
            }
        }

        if (declining.isNotEmpty()) {
            item {
                KeywordSectionHeader(
                    title = "Declining",
                    subtitle = "${declining.size} keywords",
                    icon = Icons.Filled.TrendingDown
                )
            }
            items(declining, key = { it.id }) { kw ->
                KeywordManageCard(keyword = kw, onArchive = { onArchiveKeyword(kw) })
            }
        }

        if (suggestions.isEmpty() && active.isEmpty() && declining.isEmpty()) {
            item {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(
                        "No keywords yet",
                        style = MaterialTheme.typography.titleMedium
                    )
                    Spacer(Modifier.height(8.dp))
                    Text(
                        "Use Add to create research keywords for better recommendations.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }

        item { Spacer(Modifier.height(72.dp)) }
    }
}
