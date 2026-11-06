function hasNewStream(previousGroups, currentGroups) {
    const known = new Set()
    for (const group of previousGroups) {
        for (const stream of group.streams)
            known.add(stream.index)
    }
    return currentGroups.some(group => group.streams.some(stream => !known.has(stream.index)))
}

function syncModel(model, items, key) {
    for (let index = 0; index < items.length; ++index) {
        const item = items[index]
        let previousIndex = index
        while (previousIndex < model.count && model.get(previousIndex)[key] !== item[key])
            ++previousIndex
        if (previousIndex === model.count) {
            model.insert(index, item)
            continue
        }
        if (previousIndex !== index)
            model.move(previousIndex, index, 1)

        const current = model.get(index)
        for (const role of Object.keys(item)) {
            if (role === "streams")
                syncModel(current.streams, item.streams, "index")
            else if (current[role] !== item[role])
                model.setProperty(index, role, item[role])
        }
    }
    if (model.count > items.length)
        model.remove(items.length, model.count - items.length)
}
