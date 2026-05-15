# **NSXAI**

**Semantic Analysis Pipeline for Knowledge Graph Embeddings**

---

## 📌 **About NSXAI**

**NSXAI** is a modular pipeline designed to transform **OWL ontologies** into **knowledge graphs (KG)** and generate **node embeddings** for machine learning tasks. It supports:

- **Extraction and conversion** of OWL ontologies to Turtle (TTL) format.
- **Inference** of implicit knowledge using semantic reasoning.
- **Knowledge graph construction** from TTL files.
- **Embedding generation** for nodes, compatible with ML models (RandomForest, XGBoost, SVM, GNNs, etc.).

The pipeline is optimized for **scalability**, **flexibility**, and **ease of integration** into larger projects.

---

---

## 🚀 **Installation**

### **1. Prerequisites**

- Python **3.9+** (recommended: 3.10 or 3.11).
- `pip` (usually included with Python).
- **Operating System**: Linux, macOS, or Windows (WSL recommended for Windows).

---

### **2. Clone the Repository**

```bash
git clone https://github.com/your-org/nsxai.git
cd nsxai
```

---

### **3. Create a Virtual Environment (`venv`)**

To avoid conflicts between the project's dependencies and your system-wide Python packages, it is **highly recommended** to use a virtual environment.

#### **Create the `venv**`

```bash
# Create a virtual environment in a `venv` folder
python -m venv venv
```

#### **Activate the `venv**`

- **Linux/macOS**:
  ```bash
  source venv/bin/activate
  ```
- **Windows (PowerShell)**:
  ```powershell
  .\venv\Scripts\activate
  ```
- **Windows (CMD)**:
  ```cmd
  venv\Scripts\activate.bat
  ```

> ✅ **Verification**: Once activated, your terminal prompt should show `(venv)` at the beginning.

#### **Deactivate the `venv**`

```bash
deactivate
```

> 💡 **Tip**:
>
> - **Never commit** the `venv/` folder to Git (it is already ignored via `.gitignore`).
> - For more advanced environment management, consider using `[pipenv](https://pipenv.pypa.io/)` or `[conda](https://docs.conda.io/)`.

---

### **4. Install Dependencies**

Once the `venv` is activated, install the dependencies with `pip`:

#### **Option 1: Basic Installation (scikit-learn backend)**

```bash
pip install -r requirements.txt
```

> ⚠️ **Note**: This uses **scikit-learn** for embeddings (centrality-based methods: PageRank, betweenness, etc.).

#### **Option 2: With PyTorch Geometric (Full GNN Support)**

If you want to use **Graph Neural Networks (GNNs)** like GraphSAGE or GAT, uncomment the `torch` and `torch-geometric` lines in `requirements.txt`, then:

```bash
pip install -r requirements.txt
```

> ⚡ **Recommended** for better performance on large graphs (requires a GPU for optimal results).

---

### **5. Configuration**

The pipeline uses a `**config.yaml**` file to define paths and parameters. Example:

```yaml
# config.yaml
owl_dir: ./data/ontologies      # Directory containing .owl files
catalog: ./catalog.xml          # Catalog file for OWL (optional)
dirs:
  ttl: ./output/ttl             # Output for owl2ttl
  inferred: ./output/inferred  # Output for infer
  kg: ./output/kg               # Output for kg (nodes.csv, edges.csv)
  embeddings: ./output/embeddings # Output for gnn (optional)
verbose: false                  # Verbose mode
quiet: false                    # Quiet mode
```

> 💡 **Tip**: Use a `.env` file to override paths if needed (e.g., `DATA_DIR=/absolute/path`).

---

---

## 🎯 **Usage**

### **1. Run a Specific Step**

```bash
# Convert OWL to TTL
python main.py --step owl2ttl

# Apply inferences
python main.py --step infer

# Build the knowledge graph
python main.py --step kg

# Generate embeddings (dimension 32)
python main.py --step gnn --dim 32
```

### **2. Run the Full Pipeline**

```bash
python main.py --step all --dim 64
```

> ⚠️ **Note**: The `--dim` argument is only used for the `gnn` step.

---

### **Full Example with `venv**`

```bash
# Activate the virtual environment
source venv/bin/activate  # Linux/macOS
# or
.\venv\Scripts\activate   # Windows

# Run the full pipeline
python main.py --step all --dim 64 -v

# Deactivate the virtual environment when done
deactivate
```

---

---

## 📂 **Project Structure**

```
nsxai/
├── main.py                  # Pipeline orchestrator
├── config.yaml             # Default configuration
├── requirements.txt        # Python dependencies
├── .gitignore              # Ignores venv/, output/, etc.
├── nsxai/
│   ├── semantic/           # Modules for owl2ttl and infer
│   │   ├── owl2ttl.py      # OWL → TTL conversion
│   │   └── hermit_infer.py # Inference with HermiT
│   ├── kg/                 # Modules for knowledge graph construction
│   │   └── kg_builder.py   # Generates nodes.csv and edges.csv
│   └── gnn/                # Modules for embeddings
│       └── gnn_model.py    # Embedding generation (PyG/sklearn)
└── output/                 # Output directory (auto-created)
    ├── ttl/                # TTL files
    ├── inferred/           # Enriched TTL files
    ├── kg/                 # nodes.csv + edges.csv
    └── embeddings/          # Embeddings (CSV/JSON/Parquet/NumPy)
```

---

---

## 🔍 **Step Details**

*(See the previous version for full details on the `owl2ttl`, `infer`, `kg`, and `gnn` steps.)*

---

---

## 🤝 **Contributing**

Contributions are welcome! Here’s how you can help:

### **1. Report a Bug**

- Open an **issue** on GitHub with:
  - A clear description of the problem.
  - Steps to reproduce.
  - Error logs (if applicable).

### **2. Suggest a Feature**

- Open an **issue** to discuss the new feature before coding.
- Fork the repository and submit a **Pull Request**.

### **3. Local Development**

1. Clone the repository:
  ```bash
   git clone https://github.com/your-org/nsxai.git
  ```
2. Create and activate a `venv`:
  ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/macOS
  ```
3. Install development dependencies:
  ```bash
   pip install -r requirements.txt -r requirements-dev.txt
  ```
4. Run tests:
  ```bash
   pytest
  ```

---

---

## 📜 **License**

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.

---

---

## 🙌 **Acknowledgments**

- **Owlready2** and **RDFLib** for ontology manipulation.
- **NetworkX** and **PyTorch Geometric** for graph processing and GNNs.
- **scikit-learn** for fallback embedding methods.

---

---

## 📞 **Contact**

For questions or suggestions, contact:

- **Email**: [your-email@example.com](mailto:your-email@example.com)
- **GitHub**: [@your-username](https://github.com/your-username)