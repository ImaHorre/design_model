# Documentation Structure

This folder contains all documentation for the stepgen design model, organized by model type and development phase.

## 📁 Organization

### **01_linear_hydraulic_model/**
Core hydraulic network model documentation (steady-state)
- `hydraulic_model_analysis.md` - Main model documentation and theory
- `hydraulic_discrepancy_investigation.md` - Analysis of model vs experimental discrepancies
- `edge_emulsion_linear_model_updates.md` - Recent improvements with expel volumes

### **02_time_state_model/**
Physics-based time-dependent modeling (addresses 5-6x frequency overprediction)
- `time_state_model_summary.md` - Complete implementation summary
- `step_emulsion_time_state_model_proposal_v2.md` - Original proposal
- `implementation_plan_time_state.md` - Development plan
- `time_state_model_analysis.md` - Analysis and validation
- `time_state_performance_optimization.md` - Performance improvements

### **03_stage_wise_model/**
Latest modeling direction (Mar 10-11, 2026)
- `v1/` - Initial stage-wise model implementation
- `v2/` - Current stage flow ideas and discussions

### **04_experimental_testing/**
Testing plans and experimental validation
- `experimental_testing_plan.md` - Comprehensive testing strategy
- `fix_experimental_testing_bugs.md` - Bug fixes and improvements
- `phase2_final_summary.md` - Experimental results summary

### **05_analysis_and_summaries/**
Recent analysis and cross-model documentation
- `model_summary.md` - Comprehensive overview of all models (Mar 10)
- `droplet_formation_analysis_plan.md` - Analysis methodology
- `promt_2.typst` - Recent analysis document

### **archive/**
Early development docs (Feb 27, 2026) - archived for reference
- Integration notes, capability summaries, early feature plans

### **guides and summaries/**
User guides and session summaries

### **implemementation plans - complete/**
Completed implementation plans and roadmaps

### **original_inputs/**
Seed documents and initial requirements

## 🕐 Timeline
- **Feb 27**: Early setup and integration
- **Mar 4-5**: Heavy development (time-state + linear model improvements)
- **Mar 5**: Experimental testing focus
- **Mar 10-11**: Stage-wise model development (current direction)

## 🔍 Quick Reference
- **Current active model**: Stage-wise (03_stage_wise_model/v2/)
- **Time-state reference**: 02_time_state_model/ (still coded, for reference)
- **Core hydraulic theory**: 01_linear_hydraulic_model/hydraulic_model_analysis.md
- **Complete model overview**: 05_analysis_and_summaries/model_summary.md