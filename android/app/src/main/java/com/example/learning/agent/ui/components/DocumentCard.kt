package com.example.learning.agent.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.example.learning.agent.data.remote.DocumentsApi

@Composable
fun DocumentCard(
    document: DocumentsApi.DocumentItem,
    isSelected: Boolean,
    isHighlighted: Boolean = false,
    onSelect: () -> Unit,
    onAddNote: () -> Unit = {},
    onOpen: () -> Unit = {},
    onRefresh: () -> Unit = {},
    onTriggerWorker: () -> Unit = {},
    onDelete: () -> Unit = {},
    onReprocess: () -> Unit = {},
    modifier: Modifier = Modifier
) {
    val borderColor = when {
        isSelected -> MaterialTheme.colorScheme.primary
        isHighlighted -> MaterialTheme.colorScheme.tertiary
        else -> MaterialTheme.colorScheme.outline.copy(alpha = 0f)
    }
    val borderWidth = if (isSelected || isHighlighted) 2.dp else 0.dp
    val hasTitle = !document.title.isNullOrBlank()
    val displayName = when {
        hasTitle -> document.title!!
        else -> document.url?.substringAfterLast('/')?.take(60) ?: "Document"
    }
    var showOptionsMenu by rememberSaveable { mutableStateOf(false) }

    Card(
        modifier = modifier
            .fillMaxWidth()
            .clickable(onClick = onSelect)
            .border(borderWidth, borderColor, MaterialTheme.shapes.medium)
            .padding(horizontal = 16.dp, vertical = 8.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        colors = CardDefaults.cardColors(
            containerColor = when {
                isSelected -> MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.5f)
                isHighlighted -> MaterialTheme.colorScheme.tertiaryContainer.copy(alpha = 0.4f)
                else -> MaterialTheme.colorScheme.surface
            }
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = displayName,
                        style = MaterialTheme.typography.titleMedium,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis
                    )
                    if (!hasTitle && !document.url.isNullOrBlank()) {
                        Text(
                            text = "Title not available",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.8f),
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
                    // Status chip: pending, running, done, failed
                    val status = (document.status ?: "unknown").lowercase()
                    val (statusLabel, statusColor) = when (status) {
                        "done", "ready" -> "Done" to MaterialTheme.colorScheme.primary
                        "pending", "queued" -> "Pending" to MaterialTheme.colorScheme.tertiary
                        "running" -> "Processing" to MaterialTheme.colorScheme.secondary
                        "failed" -> "Failed" to MaterialTheme.colorScheme.error
                        else -> status.replaceFirstChar { it.uppercase() } to MaterialTheme.colorScheme.outline
                    }
                    Surface(
                        color = statusColor.copy(alpha = 0.2f),
                        shape = MaterialTheme.shapes.small
                    ) {
                        Text(
                            text = statusLabel,
                            style = MaterialTheme.typography.labelSmall,
                            color = statusColor,
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                        )
                    }
                    if (isSelected) {
                        Surface(
                            color = MaterialTheme.colorScheme.primary,
                            shape = MaterialTheme.shapes.small
                        ) {
                            Text(
                                text = "Selected",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onPrimary,
                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                            )
                        }
                    }
                    Box {
                        IconButton(onClick = { showOptionsMenu = true }) {
                            Icon(
                                imageVector = Icons.Default.MoreVert,
                                contentDescription = "More options"
                            )
                        }
                        DropdownMenu(
                            expanded = showOptionsMenu,
                            onDismissRequest = { showOptionsMenu = false }
                        ) {
                            DropdownMenuItem(
                                text = { Text("Re-process") },
                                onClick = {
                                    showOptionsMenu = false
                                    onReprocess()
                                }
                            )
                            DropdownMenuItem(
                                text = {
                                    Text("Delete", color = MaterialTheme.colorScheme.error)
                                },
                                onClick = {
                                    showOptionsMenu = false
                                    onDelete()
                                }
                            )
                        }
                    }
                }
            }

            // One-sentence summary (backend: S1_TLDR_MAX_CHARS=150) — allow wrap so full text visible
            (document.tldr?.takeIf { it.isNotBlank() })?.let { tldr ->
                Text(
                    text = tldr,
                    style = MaterialTheme.typography.bodyMedium,
                    maxLines = 5,
                    overflow = TextOverflow.Ellipsis,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 8.dp, bottom = 4.dp)
                )
            }

            // Ingest date below summary (small)
            document.created_at?.takeIf { it.isNotBlank() }?.let { raw ->
                val dateOnly = raw.take(10) // ISO "2025-03-01" or "2025-03-01T..."
                if (dateOnly.length >= 10) {
                    Text(
                        text = "Ingested: $dateOnly",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.8f),
                        modifier = Modifier.padding(top = 2.dp, bottom = 4.dp)
                    )
                }
            }

            // Key points: up to 3 (backend: S1_BULLETS_COUNT=3), allow wrap per bullet
            (document.bullets?.filter { it.isNotBlank() }?.take(3))?.forEach { bullet ->
                Row(
                    modifier = Modifier.padding(vertical = 2.dp),
                    verticalAlignment = Alignment.Top
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
                        maxLines = 3,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f)
                    )
                }
            }

            if (!document.bullets.isNullOrEmpty() || !document.tldr.isNullOrBlank()) {
                Spacer(modifier = Modifier.height(12.dp))
            }

            // Optional: page count only (source_type url/pdf_url display removed)
            document.pages?.let { count ->
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "$count pages",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                val isNotDone = (document.status?.lowercase() ?: "") !in listOf("done", "ready")
                if (isNotDone) {
                    TextButton(onClick = onRefresh) {
                        Text("Refresh")
                    }
                    TextButton(onClick = onTriggerWorker) {
                        Text("Process")
                    }
                }
                TextButton(onClick = onAddNote) {
                    Text("Add Note")
                }
                TextButton(onClick = onOpen) {
                    Text("Open")
                }
            }
        }
    }
}
