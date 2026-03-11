# Fix Critical Bugs in Experimental Testing Framework

## Context

The experimental testing framework has been implemented but contains critical bugs that prevent accurate analysis. Three major issues were discovered:

1. **Critical Unit Conversion Bug**: Flow rate conversion error causing frequencies 10-100x higher than experimental data (19-254 Hz vs 0.8-3.7 Hz expected)
2. **Performance Bottleneck**: Time-state simulations take 12+ minutes due to 2 expensive hydraulic solves per timestep
3. **Testing Methodology Gap**: Using mean frequency instead of per-rung frequencies, potentially masking spatial accuracy issues

These issues must be fixed before continuing with the systematic experimental testing phases outlined in the original plan.

## Critical Bugs Identified

### 1. Unit Conversion Error (CRITICAL)
**Location**: `stepgen/testing/duty_factor_analyzer.py` line 219
**Problem**:
```python
Qw_m3s = Qw / (1e6 / 3600.0)  # WRONG - Inverts the conversion
```
**Should be**:
```python
Qw_m3s = Qw * (1e-6 / 3600.0)  # CORRECT - From config.py
```
**Impact**: Flow rates inflated by ~13 million times, causing frequency predictions 10-100x too high

### 2. Performance Bottleneck
**Location**: `stepgen/models/time_state/time_state_dfu.py` lines 138 & 157
**Problem**: Two expensive sparse matrix solves per timestep
- 750 timesteps × 2 solves = 1500 sparse LU decompositions = 12+ minutes
- Each solve rebuilds and factors sparse matrix (O(N³) operation)
**Impact**: Makes time-state model evaluation impractical

### 3. Testing Methodology Issue
**Location**: `stepgen/testing/duty_factor_analyzer.py` line 246
**Problem**: Using mean frequency across all rungs instead of per-rung frequencies like existing validation code
**Impact**: May miss position-dependent accuracy issues

## Implementation Plan

### Phase 1: Fix Critical Unit Conversion Bug (HIGH PRIORITY)

**Files to modify**:
- `stepgen/testing/duty_factor_analyzer.py`
- `stepgen/testing/time_state_evaluator.py`
- `stepgen/testing/pcap_verifier.py`

**Changes**:
1. Replace manual unit conversion with standard utility functions:
   ```python
   from stepgen.config import mlhr_to_m3s, mbar_to_pa
   Po_Pa = mbar_to_pa(Po)
   Qw_m3s = mlhr_to_m3s(Qw)
   ```

2. Update all testing modules to use consistent conversion patterns
3. Verify conversions match existing validation code in `stepgen/io/experiments.py`

### Phase 2: Fix Testing Methodology (MEDIUM PRIORITY)

**Files to modify**:
- `stepgen/testing/duty_factor_analyzer.py`

**Changes**:
1. Extract per-rung frequencies instead of using mean frequency:
   ```python
   # Get duty factor model's per-rung frequencies
   frequencies_array = duty_factor_result.frequency_hz
   if isinstance(frequencies_array, np.ndarray):
       pred_freq = frequencies_array[idx] if idx < len(frequencies_array) else np.mean(frequencies_array)
   else:
       pred_freq = frequencies_array
   ```

2. Implement solver result caching like `compare_to_predictions()` does to avoid redundant calculations
3. Update error calculation to use position-specific predictions

### Phase 3: Address Performance Issues (MEDIUM PRIORITY)

**Files to analyze and potentially modify**:
- `stepgen/models/time_state/time_state_dfu.py`
- `stepgen/models/time_state/time_state_filling.py`

**Approach**:
1. **Immediate fix**: Cache hydraulic solve results to eliminate redundant solves when system state doesn't change
2. **Optimize timestep**: Increase default dt_ms from 2.0 to 5.0-10.0 for testing purposes
3. **Early termination**: Detect steady-state and exit early
4. **Progress improvements**: Add better time estimates to progress bars

**Implementation strategy**:
- Modify time integration loop to check if conductances changed since last solve
- Only perform second solve if rung classifications actually changed
- Add adaptive timestep logic for stable phases

### Phase 4: Validation and Testing

**Test the fixes**:
1. **Unit conversion validation**:
   ```bash
   python stepgen/cli.py test-duty-factor configs/w11.yaml data/w11_4_7.csv --output-dir validation_test
   ```
   - Expected: Frequencies in 0.8-3.7 Hz range matching experimental data
   - Verify: Error calculations make sense (not 10-100x off)

2. **Performance validation**:
   ```bash
   python stepgen/cli.py test-time-state configs/w11.yaml data/w11_4_7.csv --output-dir performance_test
   ```
   - Expected: Reasonable execution time (< 5 minutes for basic test)
   - Verify: Progress bars show meaningful estimates

3. **Cross-validation with existing tools**:
   ```bash
   python stepgen/cli.py compare configs/w11.yaml data/w11_4_7.csv --out reference_comparison.csv
   ```
   - Compare results with fixed testing framework results
   - Ensure consistency with existing validation patterns

### Phase 5: Resume Systematic Testing Plan

Once bugs are fixed, resume the original experimental testing plan phases:

1. **Complete Phase 2: Duty Factor Cross-Condition Analysis**
   - With correct unit conversions, analyze if single duty factor works across conditions
   - Investigate position-dependent duty factor variations
   - Analyze error patterns vs Po/Qw changes

2. **Continue to Phase 3: Time-State Model Evaluation**
   - With improved performance, run parameter sensitivity analysis
   - Compare time-state vs linear baseline performance
   - Generate model improvement recommendations

3. **Proceed through remaining phases** as originally planned

## Key Files to Modify

**Critical fixes**:
- `stepgen/testing/duty_factor_analyzer.py:219` - Fix unit conversion bug
- `stepgen/testing/duty_factor_analyzer.py:246` - Use per-rung frequencies
- `stepgen/testing/time_state_evaluator.py:330-333` - Fix unit conversions
- `stepgen/testing/pcap_verifier.py` - Fix any unit conversion issues

**Performance improvements**:
- `stepgen/models/time_state/time_state_dfu.py:138,157` - Optimize double solves
- `stepgen/models/time_state/time_state_filling.py:141,160` - Optimize double solves

## Success Criteria

1. **Unit conversion fix**: Frequency predictions match experimental range (0.8-3.7 Hz)
2. **Performance improvement**: Time-state evaluation completes in < 5 minutes for basic testing
3. **Testing accuracy**: Per-rung frequency analysis provides spatial accuracy insights
4. **Consistency**: Results match existing validation patterns from `stepgen/io/experiments.py`
5. **Framework completion**: All originally planned testing phases can run successfully

## Verification Strategy

1. **Before/after comparison**: Run same test with old vs fixed framework
2. **Reference validation**: Compare with existing `compare` CLI command results
3. **End-to-end test**: Run full experimental testing suite successfully
4. **Performance benchmark**: Measure execution time improvements for time-state models
5. **Accuracy validation**: Verify frequency predictions are in reasonable range vs experimental data