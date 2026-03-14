package com.example.learning.agent.ui.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.navArgument
import com.example.learning.agent.ui.screens.ask.AskScreen
import com.example.learning.agent.ui.screens.feed.FeedDetailScreen
import com.example.learning.agent.ui.screens.feed.FeedScreen
import com.example.learning.agent.ui.screens.feed.IngestFailureInfo
import com.example.learning.agent.ui.screens.map.WeeklySummaryDetailScreen
import com.example.learning.agent.ui.screens.map.WeeklySummaryScreen
import com.example.learning.agent.ui.screens.notes.NotesScreen
import com.example.learning.agent.ui.screens.recommendations.RecommendationsScreen

@Composable
fun AppNavHost(
    navController: NavHostController,
    selectedDocumentId: String? = null,
    selectedDocumentTitle: String? = null,
    onDocumentSelect: (id: String, title: String?) -> Unit = { _, _ -> },
    onDocumentDeselect: () -> Unit = {},
    onDocumentDeleted: (documentId: String) -> Unit = {},
    onAskAboutDocument: (id: String, title: String?) -> Unit = { _, _ -> },
    addIngestFailure: (IngestFailureInfo) -> Unit = {},
    refreshFeedTrigger: Int = 0,
    onRefreshDone: () -> Unit = {},
    modifier: Modifier = Modifier
) {
    NavHost(
        navController = navController,
        startDestination = Destination.Feed.route,
        modifier = modifier
    ) {
        composable(Destination.Feed.route) {
            FeedScreen(
                selectedDocumentId = selectedDocumentId,
                onDocumentSelect = onDocumentSelect,
                onDocumentDeselect = onDocumentDeselect,
                onDocumentDeleted = onDocumentDeleted,
                onCardClick = { id ->
                    navController.navigate(Destination.FeedDetail.createRoute(id))
                },
                addIngestFailure = addIngestFailure,
                refreshFeedTrigger = refreshFeedTrigger,
                onRefreshDone = onRefreshDone
            )
        }
        composable(
            route = Destination.FeedDetail.route,
            arguments = listOf(
                navArgument("id") {
                    type = NavType.StringType
                }
            )
        ) { backStackEntry ->
            val id = backStackEntry.arguments?.getString("id") ?: ""
            FeedDetailScreen(
                id = id,
                onBack = { navController.popBackStack() },
                onAskAboutThis = onAskAboutDocument
            )
        }
        composable(Destination.Ask.route) {
            AskScreen(
                selectedDocumentId = selectedDocumentId,
                selectedDocumentTitle = selectedDocumentTitle,
                onDocumentSelect = onDocumentSelect,
                onDocumentDeselect = onDocumentDeselect
            )
        }
        composable(Destination.Notes.route) {
            NotesScreen()
        }
        composable(Destination.Map.route) {
            WeeklySummaryScreen(
                onOpenSummary = { id ->
                    navController.navigate(Destination.S2Detail.createRoute(id))
                }
            )
        }
        composable(
            route = Destination.S2Detail.route,
            arguments = listOf(
                navArgument("id") { type = NavType.StringType }
            )
        ) { backStackEntry ->
            val id = backStackEntry.arguments?.getString("id") ?: ""
            WeeklySummaryDetailScreen(
                id = id,
                onBack = { navController.popBackStack() }
            )
        }
        composable(Destination.Recommendations.route) {
            RecommendationsScreen()
        }
    }
}

@Composable
fun getCurrentRoute(navController: NavHostController): String? {
    val navBackStackEntry by navController.currentBackStackEntryAsState()
    return navBackStackEntry?.destination?.route
}

