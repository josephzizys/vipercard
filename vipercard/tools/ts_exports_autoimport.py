
# ts_exports_autoimport.py
# Ben Fisher, 2017

from ts_exports_read import *
import os
import re
from collections import OrderedDict

def layerPathToFilePath(srcdirectory, s):
    return srcdirectory + '/' + s + '.ts'

def readLayers(srcdirectory):
    dictFilesSeen = {}
    
    layersOfFiles = []
    counter = 0
    f = open(srcdirectory + '/layers.ts')
    currentDir = None
    for line in f:
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('/*') or line.startswith('*/') or line.startswith('import '):
            continue
        elif line.startswith('/'):
            currentDir = line
        elif line == 'testRegistrationRelease':
            continue
        else:
            counter += 1
            assertTrue(not '.' in line, line)
            curfilename = currentDir + line
            assertTrue(curfilename.startswith('/'), curfilename)
            curfilename = curfilename[1:]
            layersOfFiles.append((curfilename, 1000 - counter))
            
            if curfilename.lower() in dictFilesSeen:
                assertTrue(False, 'listed twice ' + curfilename)
            if not exists(layerPathToFilePath(srcdirectory, curfilename)):
                assertTrue(False, f'file not found {curfilename} ({layerPathToFilePath(srcdirectory, curfilename)})')
            
            dictFilesSeen[curfilename.lower()] = True
    
    # check for files missing from layers.ts
    for fname, short in recursefiles(srcdirectory):
        if short.endswith('.ts') and not '.debug.' in short and not '.ship.' in short:
            if short != 'testRegistrationRelease.ts':
                assertTrue(fname.startswith(srcdirectory), fname)
                relpath = fname[len(srcdirectory):]
                relpath = relpath.replace('\\', '/')
                assertTrue(relpath.startswith('/'), relpath)
                relpath = relpath[1:].replace('.ts', '')
                assertTrue(relpath.lower() in dictFilesSeen, 'missing from layers.ts: ' + fname, relpath)
    
    # check unique filenames
    checkUnique = {}
    for layer in layersOfFiles:
        leafname = os.path.split(layer[0])[-1].lower()
        if leafname in checkUnique:
            assertTrue(False, 'non-unique filename ' + leafname)
        checkUnique[leafname] = True
    
    layersOfFiles.sort(key=lambda item: item[1])
    return layersOfFiles


def enforceLayering(srcdirectory):
    print('running enforceLayering...')
    layers = readLayers(srcdirectory)
    for layer in layers:
        # read file
        fpath = layerPathToFilePath(srcdirectory, layer[0])
        basefilecontents = myfilesreadall(fpath)
        
        # this layer should not be able to import from anything above it
        disallowImportsFromGreaterThan = layer[1]
        for jlayer in layers:
            if jlayer[1] > disallowImportsFromGreaterThan:
                # check that the current layer didn't import from this greaterthan one
                disallowedfilename = os.path.split(jlayer[0])[-1]
                
                # disallow "example.js", allow "_example.js_"
                if re.search(r'\b' + disallowedfilename + r'\.[\s\S][\s\S][^_]', basefilecontents):
                    warn(f'file {layer[0]} referred to a layer above it {disallowedfilename} ({jlayer[0]})')


def autoAddImports(srcdirectory):
    layers = readLayers(srcdirectory)
    mapSymbolNameToLayer = {}
    
    # get a map of symbol to filename where exported from
    for layer in layers:
        fpath = layerPathToFilePath(srcdirectory, layer[0])
        symbolsInLayer = collectExports(fpath)
        if fpath.lower().endswith('testregistrationempty.ts'):
            continue
            
        for symbol in symbolsInLayer:
            symbol = symbol.strip()
            if symbol:
                if symbol in mapSymbolNameToLayer:
                    prevFound = mapSymbolNameToLayer[symbol]
                    assertTrue(symbol == 'runTestsImpl', f'dupe symbol in both {prevFound[0]} and {layer[0]}', symbol)
                mapSymbolNameToLayer[symbol] = layer
    
    # add the imports
    for layer in layers:
        print(f'{layer[0]}')
        
        short = os.path.split(layer[0])[-1]
        if short.startswith('bridge') or short.lower().endswith('testregistrationempty'):
            continue
        
        fpath = layerPathToFilePath(srcdirectory, layer[0])
        alltxt = myfilesreadall(fpath)
        lines = alltxt.replace('\r\n', '\n').split('\n')
        alreadyImported = readAlreadyImportedNotByUs(lines)
        
        addNewForThisFile = []
        for line in lines:
            if not line.startswith('import ') and not line.startswith('/* auto */ import'):
                for symbol in getSymbolsFromLine(line):
                    if symbol in alreadyImported:
                        continue
                    
                    foundFromExports = mapSymbolNameToLayer.get(symbol, None)
                    if foundFromExports is not None:
                        if foundFromExports[0] == layer[0]:
                            pass # we don't need to import from ourself
                        else:
                            addNewForThisFile.append((symbol, foundFromExports[0], foundFromExports[1]))
        
        addNewForThisFile.sort()
        # remove duplicates
        addNewForThisFile = list(OrderedDict.fromkeys(addNewForThisFile))
        # sort by level , low-level to high-level
        addNewForThisFile.sort(reverse=False, key=lambda item:item[2])
        
        whatToAdd = []
        currentFilename = None
        for symbol, foundFromExports0, foundFromExports1 in addNewForThisFile:
            if currentFilename!=foundFromExports0:
                whatToAdd.append([foundFromExports0])
                currentFilename = foundFromExports0
            whatToAdd[-1].append(symbol)
        
        newLinesToAdd = []
        for parts in whatToAdd:
            srcfile = parts[0]
            theImports = parts[1:]
            s = f'''/* auto */ import {{ {', '.join(theImports)} }} from '../../{srcfile}.js';'''
            newLinesToAdd.append(s)
        
        if newLinesToAdd:
            linesWithNoAuto = [line for line in lines if not (line.startswith('/* auto */ import') and '{' in line )]
            assertTrue(linesWithNoAuto[0]=='', 'expected file to start with an empty line '+layer[0])
            addNewLine = linesWithNoAuto[1]!=''
            if addNewLine:
                newLinesToAdd.append('')
            linesWithNoAuto[1:1] = newLinesToAdd
            
            doSomeAutomaticFormatting(linesWithNoAuto)
            alltxtNew = '\n'.join(linesWithNoAuto)
            if alltxtNew != alltxt:
                print('Writing')
                print('\n'.join(newLinesToAdd))
                myfileswriteall(fpath, alltxtNew)


def doSomeAutomaticFormatting(lines):
    if lines[-1] != '':
        print('adding final blank line')
        lines.append('')
    
    for i in range(len(lines)):
        stripped = lines[i].rstrip()
        if lines[i] != stripped:
            print('removing whitespace on right of line')
        lines[i] = stripped

def getSymbolsFromLine(s):
    for m in re.finditer(r'''(^|[^'"`a-zA-Z_])([a-zA-Z_][0-9a-zA-Z_]*)''', s):
        yield m.group(2)

testinput = '''abc, def, ghi, v1'''
expected = ['abc', 'def', 'ghi', 'v1']
assertEq(expected, list(getSymbolsFromLine(testinput)))
testinput = '''  x = myFn('', h.walkNext(), 'GO|');'''
expected = ['x', 'myFn', 'h', 'walkNext']
assertEq(expected, list(getSymbolsFromLine(testinput)))
testinput = ''' 's1', `s2`, "s3" '''
expected = []
assertEq(expected, list(getSymbolsFromLine(testinput)))

if __name__ == '__main__':
    srcdirectory = '../vipercard/src'
    layers = readLayers(srcdirectory)
    autoAddImports(srcdirectory)
    enforceLayering(srcdirectory)

    