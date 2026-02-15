package com.example.learning.agent.ui.screens.recommendations

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.learning.agent.data.repository.FakeRepository
import com.example.learning.agent.ui.components.RecommendationCard
import com.example.learning.agent.ui.theme.TekLearningAgentTheme

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RecommendationsScreen(
    modifier: Modifier = Modifier
) {
    var selectedMonth by remember { mutableStateOf("This Month") }
    var selectedTopic by remember { mutableStateOf<String?>(null) }
    
    val months = listOf("This Month", "Last Month")
    val topics = FakeRepository.getTopics()
    val recommendations = FakeRepository.getRecommendations(selectedMonth)
    
    val filteredRecommendations = remember(selectedTopic, recommendations) {
        if (selectedTopic == null) {
            recommendations
        } else {
            recommendations.filter { it.topic == selectedTopic }
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(16.dp)
    ) {
        // Month dropdown
        var expandedMonth by remember { mutableStateOf(false) }
        ExposedDropdownMenuBox(
            expanded = expandedMonth,
            onExpandedChange = { expandedMonth = !expandedMonth },
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 16.dp)
        ) {
            OutlinedTextField(
                value = selectedMonth,
                onValueChange = {},
                readOnly = true,
                label = { Text("Time Range") },
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expandedMonth) },
                modifier = Modifier
                    .fillMaxWidth()
                    .menuAnchor()
            )
            ExposedDropdownMenu(
                expanded = expandedMonth,
                onDismissRequest = { expandedMonth = false }
            ) {
                months.forEach { month ->
                    DropdownMenuItem(
                        text = { Text(month) },
                        onClick = {
                            selectedMonth = month
                            expandedMonth = false
                        }
                    )
                }
            }
        }

        // Topic chips
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState())
                .padding(bottom = 16.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            FilterChip(
                selected = selectedTopic == null,
                onClick = { selectedTopic = null },
                label = { Text("All") }
            )
            topics.forEach { topic ->
                FilterChip(
                    selected = selectedTopic == topic,
                    onClick = { 
                        selectedTopic = if (selectedTopic == topic) null else topic
                    },
                    label = { Text(topic) }
                )
            }
        }

        // Recommendations list
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(vertical = 8.dp)
        ) {
            items(filteredRecommendations.size) { index ->
                RecommendationCard(
                    recommendation = filteredRecommendations[index],
                    onThumbsUp = { /* TODO */ },
                    onThumbsDown = { /* TODO */ },
                    onSave = { /* TODO */ },
                    onDismiss = { /* TODO */ }
                )
            }
        }
    }
}

@Preview(showBackground = true)
@Composable
fun RecommendationsScreenPreview() {
    TekLearningAgentTheme {
        RecommendationsScreen()
    }
}

