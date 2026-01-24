# GLM Model Switching

We'll add a new feature for GLM chat that will let you configure which model to use for your responses.

!!! Note: this behavior will also be adapted to the base driver, with DeepSeek simply being an exemption (as it doesn't have multiple models to choose from, while our future providers like Qwen and Moonshot will have multiple models).

## What is the current model?

There's a <button> element, one of its classes is `modelSelectorButton`. As its child there's a <div>, with the first element of it being text (in DevTools it's shown as "TextNode"). That text is the current model name.

## How to change the model?

This is pretty complicated.

1. Click on the model selector button. This will open a dropdown menu with the list of available models.
2. The dropdown is a <div> that has the id `f8T9iEf1QC`. To verify, its first child is another <div> with the text "Model".
3. As a sibling of that <div> (the one with text "Model"), there's another <div> that contains the list of models.
4. Each model is a <button> element. Each of them has a `data-value` attribute, whose value is the model name.
5. We must click the button whose `data-value` matches the model we want to select.

For now we support GLM-4.7 and GLM-4.6.

Mapping:

| Friendly Name | data-value Attribute |
| -------------- | -------------------- |
| GLM-4.7       | glm-4.7               |
| GLM-4.6       | GLM-4-6-API-V1        |

*NOTE*: There's also GLM-4.6v, but we do NOT want to use it as it's horrible for roleplay.

*NOTE 2*: The data-value attribute is case-sensitive.

*NOTE 3*: Both 4.7 and 4.6 support deepthink/web access, so no need to have separate models for that.

## Implementation Notes

- We must make sure to wait for the dropdown to appear after clicking the model selector button.
- We must handle the case where the desired model is already selected (in which case we do nothing).
- We must handle the case where the desired model is not available (in which case we should log an error and select the first available model).
- We must close the dropdown after selecting the model (by clicking the model selector button again).

## Config Location

We'll put the model selection in the GLM behavior config at the top.