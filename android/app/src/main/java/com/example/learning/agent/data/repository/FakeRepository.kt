package com.example.learning.agent.data.repository

import com.example.learning.agent.data.models.Note
import com.example.learning.agent.data.models.Recommendation
import com.example.learning.agent.data.models.SummaryCard

object FakeRepository {
    fun getFeedItems(): List<SummaryCard> = listOf(
        SummaryCard(
            id = "1",
            title = "Understanding Large Language Models: A Comprehensive Guide",
            tldr = "This article explores the architecture and training methodologies of modern LLMs, focusing on transformer-based models and their applications in various domains.",
            bullets = listOf(
                "Transformer architecture revolutionized NLP",
                "Training requires massive datasets and compute",
                "Fine-tuning enables domain-specific applications"
            ),
            source = "arXiv",
            readTime = "5 min",
            fullContent = """
                Large Language Models (LLMs) have transformed the field of natural language processing. 
                This comprehensive guide covers the transformer architecture, training methodologies, 
                and practical applications of modern LLMs.
                
                The transformer architecture, introduced in "Attention Is All You Need," uses self-attention 
                mechanisms to process sequences in parallel, making it highly efficient for training.
                
                Training LLMs requires massive datasets, often containing billions of tokens, and significant 
                computational resources. The process involves pre-training on a diverse corpus followed by 
                fine-tuning for specific tasks.
                
                Applications range from text generation and translation to code completion and question answering. 
                The versatility of LLMs makes them valuable tools across many industries.
            """.trimIndent()
        ),
        SummaryCard(
            id = "2",
            title = "Neural Network Optimization Techniques",
            tldr = "An overview of optimization algorithms used in deep learning, including gradient descent variants and adaptive learning rate methods.",
            bullets = listOf(
                "Adam optimizer combines momentum and RMSprop",
                "Learning rate scheduling improves convergence",
                "Gradient clipping prevents exploding gradients"
            ),
            source = "Medium",
            readTime = "4 min",
            fullContent = """
                Neural network optimization is crucial for training effective models. This article explores 
                various optimization techniques that have become standard in deep learning.
                
                Gradient descent and its variants form the foundation of neural network optimization. 
                Stochastic gradient descent (SGD) processes data in batches, making it suitable for large datasets.
                
                Adaptive optimizers like Adam and RMSprop adjust learning rates per parameter, often leading 
                to faster convergence. These methods maintain running averages of gradients and squared gradients.
                
                Learning rate scheduling can significantly impact training. Techniques like cosine annealing 
                and warm restarts help models escape local minima and achieve better generalization.
            """.trimIndent()
        ),
        SummaryCard(
            id = "3",
            title = "Introduction to Compiler Design",
            tldr = "A beginner-friendly guide to compiler construction, covering lexical analysis, parsing, and code generation.",
            bullets = listOf(
                "Lexical analysis converts source code to tokens",
                "Parsing builds abstract syntax trees",
                "Code generation produces target machine code"
            ),
            source = "Coursera",
            readTime = "3 min",
            fullContent = """
                Compilers are essential tools that translate high-level programming languages into machine code. 
                Understanding compiler design is fundamental for computer science students and software engineers.
                
                The compilation process consists of several phases: lexical analysis, syntax analysis, semantic 
                analysis, optimization, and code generation. Each phase transforms the program representation.
                
                Lexical analysis, or tokenization, breaks source code into meaningful units called tokens. 
                This phase handles whitespace, comments, and identifies keywords and identifiers.
                
                Parsing analyzes the token stream to determine the program's structure according to the language's 
                grammar. This produces an abstract syntax tree (AST) that represents the program's hierarchical structure.
            """.trimIndent()
        )
    )

    fun getNotes(): List<Note> = listOf(
        Note(
            id = "n1",
            title = "LLM Architecture Notes",
            content = "Key points about transformer architecture and attention mechanisms.",
            tags = listOf("AI", "Machine Learning"),
            createdAt = "2024-01-15",
            source = "AI"
        ),
        Note(
            id = "n2",
            title = "Research Paper Summary",
            content = "Summary of the latest research on neural network optimization.",
            tags = listOf("Research", "Deep Learning"),
            createdAt = "2024-01-14",
            source = "Research"
        ),
        Note(
            id = "n3",
            title = "Compiler Design Concepts",
            content = "Important concepts from the compiler design course.",
            tags = listOf("Compilers", "Computer Science"),
            createdAt = "2024-01-13",
            source = null
        )
    )

    fun getRecommendations(month: String = "This Month"): List<Recommendation> = listOf(
        Recommendation(
            id = "r1",
            topicName = "This Week",
            weekStart = "2026-03-03",
            title = "Advanced Transformer Architectures",
            abstract = "A survey of recent advances in transformer architectures for NLP.",
            url = "https://arxiv.org/abs/2401.00001",
            source = "arXiv",
            score = 0.92f,
            createdAt = "2026-03-01T12:00:00Z"
        ),
        Recommendation(
            id = "r2",
            topicName = "This Week",
            weekStart = "2026-03-03",
            title = "Modern Compiler Construction",
            abstract = "Techniques for building optimizing compilers.",
            url = "https://arxiv.org/abs/2401.00002",
            source = "arXiv",
            score = 0.85f,
            createdAt = "2026-03-01T12:00:00Z"
        )
    )

    fun getTopics(): List<String> = listOf(
        "AI & Society",
        "Compilers",
        "GPUs",
        "Machine Learning",
        "Systems"
    )
}

