
# 📝 Markdown Cheatsheet

---

## 📄 Basic Formatting

| Element                     | Syntax                                      |
| --------------------------- | ------------------------------------------- |
| **Bold**              | `**text**` or `__text__`                |
| *Italic*                  | `*text*` or `_text_`                    |
| ***Bold & Italic*** | `***text***`                              |
| ~~Strikethrough~~          | `~~text~~`                                |
| `Inline Code`             | `` `code` ``                                |
| Subscript                   | `H~2~O` → H~2~O                         |
| Superscript                 | `X^2^` → X^2^                            |
| Highlight                   | `==text==` (supported in many editors)    |
| Line Break                  | End line with**2 spaces** or `<br>` |
| Horizontal Rule             | `---` / `***` / `___`                 |

---

## 🏷️ Headings

```markdown
# H1 — Largest
## H2
### H3
#### H4
##### H5
###### H6 — Smallest
```

---

## 📋 Lists

### Unordered List

```markdown
- Item 1
- Item 2
  - Nested item
* Alternative bullet
+ Another style
```

### Ordered List

```markdown
1. First step
2. Second step
   1. Sub-step
   2. Sub-step
3. Third step
```

### Task List

```markdown
- [x] Completed task
- [ ] Pending task
- [ ] To do later
```

---

## 🔗 Links & Media

| Type           | Syntax                                      |
| -------------- | ------------------------------------------- |
| Hyperlink      | `[Link Text](https://url.com)`            |
| With Title     | `[Text](url "Tooltip text")`              |
| Image          | `![Alt Text](image-url.jpg)`              |
| Reference Link | `[Text][ref]` then `[ref]: url "title"` |

---

## 📊 Tables

```markdown
| Heading 1 | Heading 2 | Heading 3 |
|---|---|---|
| Left | Center | Right |
| Cell A | Cell B | Cell C |
```

Alignment:

- `---` = Left
- `:---:` = Center
- `---:` = Right

---

## 💻 Code Blocks

### Inline Code

`` `code here` ``

### Fenced Block

```markdown
```language
function example() {
  return "Syntax highlighting";
}
```

```

### Indented Block
```

    4 spaces indent
    = code block

```

---

## 🧱 Blockquotes
```markdown
> Standard quote
> > Nested quote
> Continued lines
```

---

## 🧩 Advanced

| Feature         | Syntax                                    |
| --------------- | ----------------------------------------- |
| Footnote        | `Text [^1]` then `[^1]: Note content` |
| Escape chars    | `\* \` \# \_ \[ \]`                     |
| Definition List | `Term\n: Definition`                    |
| HTML            | Mixed HTML works:`<b>bold</b>`          |

---

## ✅ Quick Reference

```
# Heading    **Bold**    *Italic*    `Code`    --- Rule
- List       [Link](url)  ![Img](src)  > Quote
```

---

I can turn this into a printable, nicely formatted PDF or HTML reference card you can keep handy — tap **Fast** and select **Pro** to get it.
