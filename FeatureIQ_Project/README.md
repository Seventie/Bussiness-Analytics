# FeatureIQ: Consumer Smartphone Preferences Analytics

**Author:** Shaik Abdus Sattar (CB.SC.U4CSE23245)

## Overview
FeatureIQ is a business analytics project designed to help smartphone manufacturers align their hardware specifications (RAM, Battery, Camera) with the actual latent desires of distinct consumer budget segments. By transitioning from intuition-based product development to a data-driven model, OEMs can optimize profit margins and consumer satisfaction.

## Project Architecture
1. **Data Collection:** E-commerce listing scraping via the Apify platform, massively augmented via synthetic generation protocols to yield 10,000 granular records.
2. **Exploratory Data Analysis:** Interactive Plotly-based discovery of multi-modal budget distributions and distinct demographic feature priorities.
3. **Machine Learning Classification:** Implementation of a robust Random Forest algorithm to predict market segments strictly off raw hardware specifications.

## Key Files
* `analysis.ipynb`: The core interactive Jupyter Notebook containing all EDA, Plotly graphs, and the Random Forest model training.
* `Case_Study_Report.md` / `.tex`: The exhaustive 10+ page academic report detailing the problem, methodology, and SOTA benchmarking.
* `data/final_dataset.csv`: The 10,000-record dataset powering the models.
