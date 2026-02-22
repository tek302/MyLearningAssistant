package com.example.learning.agent.ui.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import com.example.learning.agent.ui.screens.ask.AskScreen
import com.example.learning.agent.ui.screens.feed.FeedDetailScreen
import com.example.learning.agent.ui.screens.feed.FeedScreen
import com.example.learning.agent.ui.screens.map.MapScreen
import com.example.learning.agent.ui.screens.notes.NotesScreen
import com.example.learning.agent.ui.screens.recommendations.RecommendationsScreen
import androidx.navigation.NavHostController
import androidx.navigation.navArgument

@Composable
fun AppNavHost(
    navController: NavHostController,
    selectedDocumentId: String? = null,
    selectedDocumentTitle: String? = null,
    onDocumentSelect: (id: String, title: String?) -> Unit = { _, _ -> },
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
                onCardClick = { id ->
                    navController.navigate(Destination.FeedDetail.createRoute(id))
                }
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
                onBack = { navController.popBackStack() }
            )
        }
        composable(Destination.Ask.route) {
            AskScreen(
                selectedDocumentId = selectedDocumentId,
                selectedDocumentTitle = selectedDocumentTitle
            )
        }
        composable(Destination.Notes.route) {
            NotesScreen()
        }
        composable(Destination.Map.route) {
            MapScreen()
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

