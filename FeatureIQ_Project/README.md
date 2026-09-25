# FeatureIQ: Predicting Consumer Smartphone Preferences and Budget Segments

**Course:** 23CSE452 Business Analytics  
**Author:** Shaik Abdus Sattar  
**Register Number:** CB.SC.U4CSE23245  

---

## 📌 Problem Statement and Objectives
The global smartphone industry suffers from a misalignment between hardware specification engineering and consumer demographic feature prioritization. Relying on intuition or retrospective sales data leads to misaligned product development and inefficient pricing/marketing strategies. 

**Objectives:**
1. Identify feature priorities (Battery, Camera, Performance) across predefined budget segments.
2. Determine key predictive hardware specifications using machine learning.
3. Formulate data-driven product strategy recommendations for R&D and marketing teams.

## 📊 Dataset Source and Collection Method
* **Collection Method:** The foundational data was collected via **web scraping** using the Apify platform, extracting live e-commerce smartphone listings and their hardware specifications.
* **Augmentation:** To achieve academic scale (10,000 records) and overcome anti-bot limitations, the scraped data was systematically augmented with synthetic consumer preference scores, simulating large-scale market surveys that correlate strictly with the scraped hardware tiers.

## 🔍 Data Preparation and Exploratory Analysis
* **Cleaning:** Handled categorical encoding for machine learning inputs. Data was validated for missing artifacts.
* **EDA Highlights:** 
  * The **Budget Distribution** chart proves the 'Mid-Range' tier represents the highest volume of consumers.
  * The **Feature Preferences** analysis visually confirms that Premium buyers heavily prioritize 'Camera/Performance', whereas Budget buyers overwhelmingly prioritize 'Battery' life.

## 🧠 Analytics Method and Implementation
* **Method:** A **Random Forest Classifier** was utilized.
* **Justification:** Hardware specifications dictate market segments in strict, non-linear tiers (e.g., 4GB RAM = Budget, 12GB = Premium). Decision trees inherently excel at mapping these strict threshold boundaries compared to linear models.
* **Implementation:** An 80/20 train-test split was applied. The model successfully classified smartphones into their correct budget segments with high accuracy and generated a robust **Feature Importance** matrix.

## 📈 Comparison with Published Studies
The implemented Random Forest model was benchmarked against three established State-of-the-Art (SOTA) methodologies found in recent predictive pricing literature:
1. **Gradient Boosting (GBM/XGBoost):** While GBM achieved similar accuracy, our Random Forest trained significantly faster and was less prone to overfitting on tabular specification data.
2. **Support Vector Machines (SVM):** SVM struggled with the overlapping multi-class boundaries and lacked the interpretability of our tree-based feature importance.
3. **Multinomial Logistic Regression:** Traditional linear models failed to map the non-linear RAM/Storage thresholds, proving our ensemble approach was definitively required.

## 💡 Results, Insights, and Recommendations
* **Insights:** Storage and RAM are the absolute gatekeepers of pricing tiers. Battery life is a budget necessity, not a premium driver.
* **Recommendations:** 
  * **R&D:** Reallocate camera budgets in budget-tier phones strictly towards massive batteries (5000mAh+).
  * **Marketing:** Cease marketing mediocre cameras to budget buyers; focus entirely on "all-day reliability".
  * **Strategy:** Use the predictive model to score prototype specifications before mass production to ensure BOM (Bill of Materials) matches the target demographic.

## 📂 Repository Structure
```text
📦 FeatureIQ_Project
 ┣ 📂 data
 ┃ ┗ 📜 final_dataset.csv          # Cleaned 10,000-record dataset
 ┣ 📂 images                       # Visualizations and Scraping Proofs
 ┣ 📂 FeatureIQ                    # Apify Scraper source files
 ┣ 📜 analysis.ipynb               # Complete Jupyter Notebook with EDA & ML pipeline
 ┣ 📜 Case_Study_Report.pdf        # Final compiled case study report
 ┣ 📜 Case_Study_Report.md         # Markdown version of the report
 ┣ 📜 Case_Study_Report.tex        # LaTeX source of the report
 ┗ 📜 README.md                    # Project overview (this file)
```
